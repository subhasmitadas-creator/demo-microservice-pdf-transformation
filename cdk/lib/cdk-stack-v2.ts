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
import * as iam from 'aws-cdk-lib/aws-iam';
import * as cr from 'aws-cdk-lib/custom-resources';
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

    // Import BetterStack SNS topics for alarm routing
    const alertHighTopic = sns.Topic.fromTopicArn(this,
        'BetterStackAlertHigh',
        `arn:aws:sns:${region}:${accountId}:BetterStackAlertHigh`
    );
    const alertLowTopic = sns.Topic.fromTopicArn(this,
        'BetterStackAlertLow',
        `arn:aws:sns:${region}:${accountId}:BetterStackAlertLow`
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

    errorAlarm.addAlarmAction(new cw_actions.SnsAction(alertHighTopic));
    errorAlarm.addOkAction(new cw_actions.SnsAction(alertHighTopic));

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

    throttledAlarm.addAlarmAction(new cw_actions.SnsAction(alertLowTopic));
    throttledAlarm.addOkAction(new cw_actions.SnsAction(alertLowTopic));

    // ------------------------------------------------------------
    // S3 buckets
    // ------------------------------------------------------------
    // Outbound bucket. This bucket is used by the pdf transformation service
    // to deliver files to Paligo - aka outbound files.
    const outboundBucket = ssm.StringParameter.valueForStringParameter(this, '/env/s3/microservice/outbound-v2');
    const inboundBucket = ssm.StringParameter.valueForStringParameter(this, '/env/s3/microservice/inbound-v2');

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

    // ------------------------------------------------------------
    // PRIVATE DNS
    // ------------------------------------------------------------
    // `<region>.pdftransformation.intern` is what clients resolve (service-paligo passes it
    // as `<region>.pdftransformation.intern:8000`). Created by the deleted v1 stack, so it
    // has been live but unmanaged since.
    //
    // UPSERT rather than AWS::Route53::RecordSet: CloudFormation can neither adopt an
    // existing record nor create one whose name is taken, so a RecordSet would mean
    // delete-then-create — a DNS gap. UPSERT is idempotent and adopts in place.
    const internZone = cdk.aws_route53.HostedZone.fromLookup(this, 'InternZone', {
      domainName: 'intern',
      privateZone: true,
    });

    const recordName = `${this.region}.pdftransformation.intern`;

    // No onDelete: destroying the stack leaves the record for clients still resolving it.
    new cr.AwsCustomResource(this, 'PdfTransformationV2ServiceRecordUpsert', {
      onUpdate: {
        service: 'Route53',
        action: 'changeResourceRecordSets',
        parameters: {
          HostedZoneId: internZone.hostedZoneId,
          ChangeBatch: {
            Comment: `Managed by ${this.stackName}`,
            Changes: [{
              Action: 'UPSERT',
              ResourceRecordSet: {
                Name: recordName,
                Type: 'CNAME',
                TTL: cdk.Duration.minutes(30).toSeconds(),
                ResourceRecords: [{
                  Value: cdk.Fn.importValue('Paligo-Foundation-ECS-Base-InternalALBDNS'),
                }],
              },
            }],
          },
        },
        // Stable across deploys, so a changed target is an update, not a replacement.
        physicalResourceId: cr.PhysicalResourceId.of(recordName),
      },
      policy: cr.AwsCustomResourcePolicy.fromStatements([
        new iam.PolicyStatement({
          actions: ['route53:ChangeResourceRecordSets'],
          resources: [internZone.hostedZoneArn],
          conditions: {
            'ForAllValues:StringEquals': {
              'route53:ChangeResourceRecordSetsRecordTypes': ['CNAME'],
              'route53:ChangeResourceRecordSetsActions': ['UPSERT'],
              'route53:ChangeResourceRecordSetsNormalizedRecordNames': [recordName],
            },
          },
        }),
      ]),
      installLatestAwsSdk: false,
    });

    // `-v2` in the parameter name only: the value stays the record managed above, which is
    // what actually resolves. Port comes from servicePort so it cannot drift from the
    // listener. v1's `/env/microservice/endpoint/pdftransformation` is left untouched.
    new ssm.StringParameter(this, 'PdfTransformationV2Endpoint', {
      parameterName: '/env/microservice/endpoint/pdftransformation-v2',
      description: 'Complete endpoint for this micro service',
      stringValue: `${recordName}:${servicePort}`,
    });
  }
}
