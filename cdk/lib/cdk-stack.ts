import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ssm from 'aws-cdk-lib/aws-ssm';
import { Repository } from 'aws-cdk-lib/aws-ecr';
import { Architecture, DockerImageCode } from 'aws-cdk-lib/aws-lambda';
import { ApplicationLoadBalancer } from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import { Construct } from 'constructs';
import { Bucket } from 'aws-cdk-lib/aws-s3';

export class CdkStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // tag all resources in this stack
    cdk.Tags.of(this).add('paligo:repository', 'https://bitbucket.org/expertinfo/microservice-pdf-transformation/src/main/');
    cdk.Tags.of(this).add('paligo:service:type', 'microservice');
    cdk.Tags.of(this).add('paligo:service:name', 'pdf-transformation');


    // Port where the alb accept requests
    const servicePort = 8000;

    // Image version to use. According to Stackoverflow, it's better to use a specific version,
    // instead of 'latest'. A specific version makes sure that the Lambda app is re-deployed
    // once the version changes.
    // https://stackoverflow.com/questions/65996593/aws-cdk-update-lambda-function-code-when-code-is-referenced-by-ecr-image
    const imageVersion = '1.0.7'

    // Import an existing VPC by its name of paligo-vpc
    // Note that the name of the VPC is the same in all
    // regions and all accounts (staging, prod)
    const paligoVpc = ec2.Vpc.fromLookup(this, 'ImportedVPC', {
      vpcName: 'paligo-vpc'
    });

    // Application Loadbalancer ARN used for internal services 
    const loadbalancerInternARN = ssm.StringParameter.valueForStringParameter(this, '/env/alb/intern/arn');

    // Security group that allows incoming traffic to the lb and the service.
    const loadbalancerSG = new ec2.SecurityGroup(this, 'LoadbalancerSecurityGroup', {
      vpc: paligoVpc,
    });

    loadbalancerSG.addIngressRule(
      ec2.Peer.ipv4(paligoVpc.vpcCidrBlock),
      ec2.Port.tcp(servicePort)
    );

    // Get the load balancer. We need to look up the ALB via the
    // ARN. Tags do not work, unfortunately
    const alb = ApplicationLoadBalancer.fromApplicationLoadBalancerAttributes(this, 'loadbalancer', {
      loadBalancerArn: loadbalancerInternARN,
      vpc: paligoVpc,
      securityGroupId: loadbalancerSG.securityGroupId
    });

    // The image - this does not work and is manually deployed
    const repo = Repository.fromRepositoryAttributes(this, "serviceRepo", {
      repositoryName: "microservice-pdftransformation",
      repositoryArn: `arn:aws:ecr:${this.region}:397662812780:repository`
    })

    // Create the lambda function and set timeout to 10 minutes
    const lambda = new cdk.aws_lambda.DockerImageFunction(this, "microservice-pdf-transformation", {
      functionName: "microservice-pdf-transformation",
      code: DockerImageCode.fromEcr(repo, {tagOrDigest: imageVersion}),
      timeout: cdk.Duration.minutes(10),
      architecture: Architecture.ARM_64,
    });

    // Outbound bucket. This bucket is used by the pdf transformation service
    // to deliver files to Paligo - aka outbound files.
    const outboundBucket = ssm.StringParameter.valueForStringParameter(this, '/env/s3/microservice/outbound');
    const inboundBucket = ssm.StringParameter.valueForStringParameter(this, '/env/s3/microservice/inbound');

    // Import s3 bucket
    let s3OutboundBucket = Bucket.fromBucketArn(this, 'outboundBucket', `arn:aws:s3:::${outboundBucket}`)
    let s3InboundBucket = Bucket.fromBucketArn(this, 'inboundBucket', `arn:aws:s3:::${inboundBucket}`)

    s3OutboundBucket.grantRead(lambda);
    s3InboundBucket.grantReadWrite(lambda);

    // Add env variables for lambda function
    lambda.addEnvironment("SERVICE_RECEIVE_BUCKET", inboundBucket);
    lambda.addEnvironment("SERVICE_DELIVERY_BUCKET", outboundBucket);

    // Create a new listener that targets the lambda function
    const listener = alb.addListener('cdk-listener', { port: servicePort });
    listener.addTargets('cdk-targets', {
      targets: [new cdk.aws_elasticloadbalancingv2_targets.LambdaTarget(lambda)],
      healthCheck: {
        enabled: true,
        path: '/status'
      }
    });

    // Last step is to add a dns record to the Route53 private zone
    const privateZone = cdk.aws_route53.HostedZone.fromLookup(this, 'private-zone', {
      domainName: 'intern',
      privateZone: true
    });

    new cdk.aws_route53.CnameRecord(this, 'service-record', {
      zone: privateZone,
      recordName: [this.region, 'pdftransformation'].join('.'),
      domainName: ssm.StringParameter.valueForStringParameter(this, '/env/alb/intern/dnsname')
    });

    // Store the entire service url in SSM parameter store
    new ssm.StringParameter(this, "PdfTransformationEndpoint", {
      parameterName: "/env/microservice/endpoint/pdftransformation",
      description: "Complete endpoint for this micro service",
      stringValue: [this.region, 'pdftransformation', 'intern'].join('.') + ':' + servicePort
    });
  }
}
