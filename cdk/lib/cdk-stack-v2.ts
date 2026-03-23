import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ssm from 'aws-cdk-lib/aws-ssm';
import { Repository } from 'aws-cdk-lib/aws-ecr';
import { Architecture, DockerImageCode } from 'aws-cdk-lib/aws-lambda';
import { ApplicationLoadBalancer } from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import { Construct } from 'constructs';
import { Bucket } from 'aws-cdk-lib/aws-s3';
import { RetentionDays } from 'aws-cdk-lib/aws-logs';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as cw_actions from 'aws-cdk-lib/aws-cloudwatch-actions';
import {
  aws_elasticloadbalancingv2 as elbv2,
} from 'aws-cdk-lib';
import {
  aws_elasticloadbalancingv2_targets as elbv2Targets,
} from 'aws-cdk-lib';

export class CdkStackV2 extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // ------------------------------------------------------------
    // TAGS
    // ------------------------------------------------------------
    cdk.Tags.of(this).add('paligo:repository', 'https://bitbucket.org/expertinfo/microservice-pdf-transformation/src/main/');
    cdk.Tags.of(this).add('paligo:service:type', 'microservice');
    cdk.Tags.of(this).add('paligo:service:name', 'pdf-transformation-v2');


    // Port where the alb accept requests
    const servicePort = 8000;

    // Image version to use. According to Stackoverflow, it's better to use a specific version,
    // instead of 'latest'. A specific version makes sure that the Lambda app is re-deployed
    // once the version changes.
    // https://stackoverflow.com/questions/65996593/aws-cdk-update-lambda-function-code-when-code-is-referenced-by-ecr-image
    const imageVersion = 'latest'

    // ------------------------------------------------------------
    // VPC v2
    // ------------------------------------------------------------
    const vpc = ec2.Vpc.fromLookup(this, 'ImportedVPC', {
      vpcName: 'paligo-vpc-v2'
    });

    // ------------------------------------------------------------
    // IMPORT EXISTING INTERNAL ALB (EXPORTS)
    // ------------------------------------------------------------
    // From ECS baseline stack
    const albArn = cdk.Fn.importValue("Paligo-Foundation-ECS-Base-InternalALBArn");

    // From Network baseline stack (ALB SG)
    const albSgId = cdk.Fn.importValue("Paligo-Foundation-VPC-Base-SgPrivateAll");

    const alb = elbv2.ApplicationLoadBalancer.fromApplicationLoadBalancerAttributes(this, 'InternalAlb', {
      loadBalancerArn: albArn,
      vpc,
      securityGroupId: albSgId,
      securityGroupAllowsAllOutbound: true,
    });

    // ------------------------------------------------------------
    // SECURE ALB SG RULE: VPC CIDR → ALB listener port (8000)
    // ------------------------------------------------------------
    const albSg = ec2.SecurityGroup.fromSecurityGroupId(this, 'AlbSecurityGroup', albSgId, {
      mutable: true,
    });

    albSg.addIngressRule(
      ec2.Peer.ipv4(vpc.vpcCidrBlock),
      ec2.Port.tcp(servicePort),
      'Allow VPC CIDR to reach pdf-transformation listener'
    );

    // ------------------------------------------------------------
    // ECR REPO (FIXED ARN — don't use the incomplete ARN from old code)
    // ------------------------------------------------------------
    const repo = Repository.fromRepositoryAttributes(this, "serviceRepo", {
      repositoryName: "microservice-pdftransformation",
      repositoryArn: `arn:aws:ecr:${this.region}:397662812780:repository/microservice-pdftransformation`
    })

    // ------------------------------------------------------------
    // LAMBDA (Docker image)
    // ------------------------------------------------------------
    const lambda = new cdk.aws_lambda.DockerImageFunction(this, "microservice-pdf-transformation-v2", {
      functionName: "microservice-pdf-transformation-v2",
      code: DockerImageCode.fromEcr(repo, {tagOrDigest: imageVersion}),
      timeout: cdk.Duration.minutes(10),
      memorySize: 1024,
      architecture: Architecture.ARM_64,
      ephemeralStorageSize: cdk.Size.gibibytes(2),
      logRetention: RetentionDays.THREE_MONTHS
    });

    // ------------------------------------------------------------
    // CW alarms, actions and SNS topic
    // ------------------------------------------------------------
    //get account and region dynamically
    const accountId = cdk.Stack.of(this).account;
    const region = cdk.Stack.of(this).region;

    // Import existing SNS topic by ARN
    const alarmTopic = sns.Topic.fromTopicArn(this,
        'ImportedAlarmTopic',
        `arn:aws:sns:${region}:${accountId}:ActionRequired`
    );

    // CloudWatch Alarm for Lambda Errors
    const errorAlarm = new cloudwatch.Alarm(this, 'LambdaErrorAlarm', {
      alarmName: `${lambda.functionName}-LambdaError`,
      metric: lambda.metricErrors({
        period: cdk.Duration.minutes(5),
        statistic: 'Sum', // total number of errors in that period
      }),
      threshold: 1, // alarm if >= 1 error
      evaluationPeriods: 1, // only one 5-minute datapoint needed
      datapointsToAlarm: 1, // alarm after first datapoint breaching threshold
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
    });

    // Add SNS topic as alarm action
    errorAlarm.addAlarmAction(new cw_actions.SnsAction(alarmTopic));

    // CloudWatch Alarm for Throttled Invocations
    const throttledAlarm = new cloudwatch.Alarm(this, 'LambdaThrottleAlarm', {
      alarmName: `${lambda.functionName}-Throttles`,
      metric: lambda.metricThrottles({
        period: cdk.Duration.minutes(5),
        statistic: 'Sum', // count total throttles in period
      }),
      threshold: 0, // threshold is > 0
      evaluationPeriods: 1, // only one 5-min datapoint needed
      datapointsToAlarm: 1, // alarm on first breach
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
    });

    // Add SNS topic as alarm action
    throttledAlarm.addAlarmAction(new cw_actions.SnsAction(alarmTopic));

    // ------------------------------------------------------------
    // S3 buckets
    // ------------------------------------------------------------
    // Outbound bucket. This bucket is used by the pdf transformation service
    // to deliver files to Paligo - aka outbound files.
    const outboundBucket = ssm.StringParameter.valueForStringParameter(this, '/env/s3/microservice/outbound');
    const inboundBucket = ssm.StringParameter.valueForStringParameter(this, '/env/s3/microservice/inbound');

    // Import s3 bucket
    let s3OutboundBucket = Bucket.fromBucketArn(this, 'outboundBucket', `arn:aws:s3:::${outboundBucket}`)
    let s3InboundBucket = Bucket.fromBucketArn(this, 'inboundBucket', `arn:aws:s3:::${inboundBucket}`)

    s3OutboundBucket.grantRead(lambda);
    s3InboundBucket.grantReadWrite(lambda);

    // ------------------------------------------------------------
    // Lambda ENV var
    // ------------------------------------------------------------
    lambda.addEnvironment("SERVICE_RECEIVE_BUCKET", inboundBucket);
    lambda.addEnvironment("SERVICE_DELIVERY_BUCKET", outboundBucket);

    // ------------------------------------------------------------
    // ALB LISTENER → LAMBDA TARGET
    // ------------------------------------------------------------
    // NOTE: SG inbound for this port must be opened on the ALB SG in NetworkBaselineStack
    // (VPC CIDR → TCP:servicePort). Don't create ad-hoc rules here.
    const listener = alb.addListener('PDFTransformationV2listener', {
      port: servicePort,
      protocol: cdk.aws_elasticloadbalancingv2.ApplicationProtocol.HTTP,
      open: false, // prevents CDK from adding 0.0.0.0/0 inbound rule 
    });

    const PDFTransformationTg = new elbv2.ApplicationTargetGroup(
      this,
      'PDFTransformationV2TargetGroup', {
        vpc,
        targetGroupName: `lambda-pdf-transform-tg-v2`.slice(0, 32), // Max 32 chars
        targetType: elbv2.TargetType.LAMBDA, // Important for Lambda
        healthCheck: {
          enabled: true,
          path: '/status',
          interval: cdk.Duration.minutes(5),
        },
      }
    );

     // Register Lambda
    PDFTransformationTg.addTarget(new elbv2Targets.LambdaTarget(lambda))

    // Attach TG to listener
    listener.addTargetGroups('PDFTransformationV2TgAttachment', {
      targetGroups: [PDFTransformationTg],
    });
  }
}
