#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { CdkStack } from '../lib/cdk-stack';
import { CdkStackV2 } from '../lib/cdk-stack-v2';

const app = new cdk.App();
new CdkStack(app, 'lambda-microservice-pdf', {
    env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: process.env.CDK_DEFAULT_REGION },
});

new CdkStackV2(app, 'PaligoLambdaPdfTransform-V2', {
    env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: process.env.CDK_DEFAULT_REGION },
});