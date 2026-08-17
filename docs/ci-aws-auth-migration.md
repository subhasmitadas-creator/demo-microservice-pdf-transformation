# Bitbucket vs GitHub AWS authentication + migration plan

For `microservice-pdf-transformation`. How CI authenticates to AWS today on Bitbucket
Pipelines, how it will work on GitHub Actions after migration, and an ordered runbook for
migrating this one repo.

**Status: for review. Nothing here has been executed.** Cutting over is a separate ticket.

All AWS values below were read from the live accounts, not from documentation.

---

## Contents

1. [Summary](#1-summary)
2. [Bitbucket → AWS today](#2-bitbucket--aws-today)
3. [GitHub → AWS after migration](#3-github--aws-after-migration)
4. [Side by side](#4-side-by-side)
5. [The translated workflow](#5-the-translated-workflow)
6. [Migration runbook](#6-migration-runbook)
7. [Findings](#7-findings)
8. [Related work already in flight](#8-related-work-already-in-flight)
9. [Decisions blocking execution](#9-decisions-blocking-execution)
10. [Local environment issues](#10-local-environment-issues)

---

## 1. Summary

Both platforms do the same thing: mint a short-lived JWT describing the CI job, exchange it for
temporary AWS credentials via `sts:AssumeRoleWithWebIdentity`, and store no long-lived keys
anywhere. The migration is not a change of mechanism — it is a change of issuer, claim format,
and one structural detail about *when* credentials become available.

For this repo the work is small:

| | |
|---|---|
| Secrets / deployment variables to migrate | **0** |
| AWS changes needed | **1** — a single IAM role |
| OIDC providers to create | **0** — both accounts already have one |
| Tracked files / branches / tags | 52 / 4 / 0 |

The repo hardcodes its account ID, role ARN and region in `bitbucket-pipelines.yml`, and has no
`deployment:` blocks. There is also no production deploy pipeline, so a failed cutover cannot
break a release path.

---

## 2. Bitbucket → AWS today

### 2.1 The mechanism

No AWS access keys exist anywhere in this repo or in Bitbucket. Authentication is OpenID
Connect: Bitbucket vouches for the pipeline step, and AWS is configured to trust that assertion.

```
Step declares  oidc: true
     │
     ▼
Bitbucket mints a short-lived JWT  →  $BITBUCKET_STEP_OIDC_TOKEN
     iss: api.bitbucket.org/2.0/workspaces/expertinfo/pipelines-config/identity/oidc
     sub: {repository-uuid}:{step-uuid}
     aud: ari:cloud:bitbucket::workspace/1d4402be-a155-4151-a60d-017a168a790c
     │
     ▼
sts:AssumeRoleWithWebIdentity  (JWT + role ARN)
     │
     ▼
AWS validates the JWT signature against the registered OIDC provider,
then evaluates the role's trust-policy conditions
     │
     ▼
Temporary credentials (max 1 hour) — nothing long-lived is ever stored
```

### 2.2 This repo's pipeline

`bitbucket-pipelines.yml` in full is one reusable step, run manually (`custom`) and on every
pull request:

```yaml
- step: &pytest
    name: Run tests
    runtime:
      cloud:
        arch: arm
    image:
      name: "397662812780.dkr.ecr.eu-west-1.amazonaws.com/microservice-pdftransformation:latest"
      aws:
        oidc-role: "arn:aws:iam::397662812780:role/bitbucket_pipeline_pdftransformation"
    oidc: true
    script:
      - echo "execute pytest"
      - poetry install
      - poetry run pytest tests --disable-warnings
```

The important detail: the credential exchange is performed by the **Bitbucket runner itself,
before the container starts**, because the runner needs credentials to pull the image from ECR.
The `script:` block never touches AWS — `poetry install` and `pytest` need no AWS access at all.

The tests confirm this: they use `unittest.mock.patch` to stub the file service
(`tests/processors/test_pdftk_processor.py:21`), and no test imports `boto3` or touches S3. AWS
is needed for exactly one thing in this pipeline: fetching the image.

### 2.3 The AWS side (account 397662812780 — Paligo Staging)

**Identity provider**

```
arn:aws:iam::397662812780:oidc-provider/api.bitbucket.org/2.0/workspaces/expertinfo/pipelines-config/identity/oidc
```

Registered once per account, scoped to the `expertinfo` workspace.

**Role** — `bitbucket_pipeline_pdftransformation`, trust policy:

```json
{
  "Effect": "Allow",
  "Principal": {
    "Federated": "arn:aws:iam::397662812780:oidc-provider/api.bitbucket.org/2.0/workspaces/expertinfo/pipelines-config/identity/oidc"
  },
  "Action": "sts:AssumeRoleWithWebIdentity",
  "Condition": {
    "StringLike": {
      "api.bitbucket.org/2.0/workspaces/expertinfo/pipelines-config/identity/oidc:sub":
        "{4fac6a60-c04b-46f7-9a50-6dff6b94d23f}:*"
    }
  }
}
```

Two layers of scoping: the provider restricts to the `expertinfo` workspace, and the `sub`
condition pins to a single repository UUID. The trailing `:*` matches any step UUID within that
repository. A different repo in the same workspace cannot assume this role.

**Permissions** — one inline policy, `bitbucket-ecr-access-all`:

| Actions | Resource |
|---|---|
| `ecr:GetAuthorizationToken`, `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer`, `ecr:BatchCheckLayerAvailability`, `ecr:DescribeImages`, `ecr:DescribeRepositories`, `ecr:GetRepositoryPolicy`, `ecr:ListImages` | `*` |

Read-only ECR. No S3, no Lambda, no deploy permissions — consistent with there being no
production deploy pipeline in this repo.

### 2.4 Three patterns in use across Paligo

| Pattern | Used by | How | Grants |
|---|---|---|---|
| **A. Declarative** | `microservice-pdf-transformation` | `image.aws.oidc-role` — runner exchanges the token pre-container | Image pull only |
| **B. Manual env vars** | `microservice-contentoutput` | writes token to a file, sets `AWS_ROLE_ARN` + `AWS_WEB_IDENTITY_TOKEN_FILE` | Full SDK access (ECR push) |
| **C. Atlassian pipe** | `paligo-cli` | `atlassian/aws-ecr-push-image` with `AWS_OIDC_ROLE_ARN` | Whatever the pipe needs |

**Pattern B** (`microservice-contentoutput/bitbucket-pipelines.yml:142-154`):

```yaml
- export AWS_REGION=eu-west-1
- export AWS_ROLE_ARN=arn:aws:iam::397662812780:role/BitbucketPipelinesOidc-microservice-contentoutput
- export AWS_WEB_IDENTITY_TOKEN_FILE=$BITBUCKET_CLONE_DIR/web-identity-token
- echo "$BITBUCKET_STEP_OIDC_TOKEN" > $AWS_WEB_IDENTITY_TOKEN_FILE
- aws sts get-caller-identity
```

Note there is no explicit `aws sts assume-role-with-web-identity` call. Setting those two
environment variables is sufficient — the AWS SDK's default credential provider chain detects
web-identity configuration and performs the exchange automatically. Worth understanding,
because the GitHub Actions equivalent works the same way under the hood.

`microservice-contentoutput` uses **both** A and B in one file: B to build and push the image,
A to pull it in later steps.

**Pattern C** (`paligo-cli/bitbucket-pipelines.yml:71-74`):

```yaml
- pipe: atlassian/aws-ecr-push-image:2.6.0
  variables:
    AWS_DEFAULT_REGION: eu-west-1
    AWS_OIDC_ROLE_ARN: arn:aws:iam::397662812780:role/BitbucketPipelinesOidc-paligo-cli
    IMAGE_NAME: paligo/cli
    TAGS: $BITBUCKET_TAG
```

### 2.5 How roles are meant to be provisioned

The `bitbucket-pipelines-auth` repo is a CDK app that owns this. From
`lib/constructs/oidc-role.ts`:

```typescript
export class OidcRole extends Role {
  public static readonly ROLE_NAME = `BitbucketPipelinesOidc-%s`;
  ...
  StringLike: { `...:sub`: `{${repositoryUuid}}:*` }
  maxSessionDuration: Duration.hours(1),
}
```

So the convention is `BitbucketPipelinesOidc-<repository-name>`, one stack per repo under
`lib/stacks/repos/<repo>/`, with repository UUIDs held centrally in
`bin/bitbucket-pipelines-auth.ts`:

```typescript
const accounts = {
  management:       '767397831725',
  production:       '393622382821',
  staging:          '397662812780',
  internalServices: '676591241865',
};
const bitbucket = {
  workspaceName: 'expertinfo',
  workspaceUuid: '1d4402be-a155-4151-a60d-017a168a790c',
  repositoryUuids: { 'ccms': ..., 'microservice-contentoutput': ..., 'paligo-cli': ..., ... },
};
```

The OIDC provider itself is created by `OidcProviderStack`, deployed per account. Its README
documents onboarding as four steps:

1. Look up the repository UUID in Bitbucket and add it to `bin/bitbucket-pipelines-auth.ts`.
2. Create a new stack in `lib/stacks/repos/<repo-name>/`.
3. Reference the stack in `bin/bitbucket-pipelines-auth.ts` with the target account's `env`.
4. If the pipeline needs an OIDC provider in a new account, add a new `OidcProviderStack`
   instance.

Deployment selects stacks by the profile's account, so `npx cdk deploy --all --profile <p>`
deploys exactly the stacks belonging to that account.

Seven repositories are onboarded today: `ccms`, `cdk-runner`, `dev-metrics`,
`infra-base-internal-services`, `microservice-contentoutput`, `paligo-cli`, `service-paligo`.
`microservice-pdf-transformation` is **not** one of them — see **F1**.

---

## 3. GitHub → AWS after migration

### 3.1 The mechanism

Structurally identical to Bitbucket. Only the issuer, the claim format, and the plumbing differ.

```
Workflow grants  permissions: id-token: write
     │
     ▼
Job requests a JWT from GitHub's token service
     iss: https://token.actions.githubusercontent.com
     sub: repo:<org>/<repo>:ref:refs/heads/<branch>      (form varies — see §3.4)
     aud: sts.amazonaws.com
     │
     ▼
aws-actions/configure-aws-credentials calls sts:AssumeRoleWithWebIdentity
     │
     ▼
AWS validates the signature against the registered OIDC provider,
then evaluates the role's trust-policy conditions
     │
     ▼
Temporary credentials exported as env vars for later steps (max 1 hour)
```

Two differences that matter in practice:

**`permissions: id-token: write` is mandatory and easy to miss.** Without it the job cannot
request a token at all, and the failure surfaces as a generic "Credentials could not be
loaded", not as a permissions error. Bitbucket has no equivalent — `oidc: true` is the whole
opt-in.

**Credentials arrive inside the job, not before it.** This is the single most consequential
difference for this repo — see §3.5.

### 3.2 What already exists in AWS

**The OIDC provider is already registered in both accounts.** No provider needs creating.

| Account | ARN | Created |
|---|---|---|
| 397662812780 (staging) | `arn:aws:iam::397662812780:oidc-provider/token.actions.githubusercontent.com` | 2025-02-07 |
| 230763337748 (playground) | `arn:aws:iam::230763337748:oidc-provider/token.actions.githubusercontent.com` | — |

Staging provider configuration:
```json
{
  "Url": "token.actions.githubusercontent.com",
  "ClientIDList": ["sts.amazonaws.com"],
  "ThumbprintList": ["d89e3bd43d5d909b47a18977aa9d5ce36cee184c"]
}
```
`ClientIDList` is the allowed `aud`, and `sts.amazonaws.com` is what
`aws-actions/configure-aws-credentials` requests by default — so no change needed.

**There is already a precedent role**, created the same day as the provider:

| Property | Value |
|---|---|
| Role | `arn:aws:iam::397662812780:role/github-actions` |
| Trust | `StringLike` on `sub` = `repo:Paligo/paligo-app:*` |
| Session | 3600s (1 hour) |
| Attached | `bitbucket-pipelines-ecr-access`, `AmazonElasticContainerRegistryPublicReadOnly` |

This settles the target-org question: the trust policy says `repo:Paligo/...`, confirming
**`Paligo` is the GitHub org**, not `expertinfo`.

### 3.3 Do not copy the precedent role

It has two problems — **F6** (ECR policy scoped to an empty region) and **F7** (bare wildcard
`sub`). Both are detailed in §7.

### 3.4 Scoping the `sub` claim

The `sub` claim's shape depends on what triggered the workflow. Choosing the condition is the
main security decision here.

| Trigger | `sub` value |
|---|---|
| Push to a branch | `repo:Paligo/<repo>:ref:refs/heads/main` |
| Tag | `repo:Paligo/<repo>:ref:refs/tags/v1.0.0` |
| Pull request | `repo:Paligo/<repo>:pull_request` |
| Environment | `repo:Paligo/<repo>:environment:production` |

The pull-request form does **not** contain the branch name — it is the literal string
`pull_request`. This matters here: today's pipeline runs on pull requests, so a condition of
only `ref:refs/heads/main` would reject exactly the case that needs to work.

Recommended condition — two exact values rather than a wildcard:

```json
"Condition": {
  "StringEquals": {
    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
  },
  "StringLike": {
    "token.actions.githubusercontent.com:sub": [
      "repo:Paligo/microservice-pdf-transformation:ref:refs/heads/main",
      "repo:Paligo/microservice-pdf-transformation:pull_request"
    ]
  }
}
```

This also adds the `aud` check that the Bitbucket roles omit (**F3**) — cheap defence in depth
on a new role, even though it is not the existing house pattern.

`pull_request` covers PRs from branches in the repo. Workflows triggered by `pull_request` from
a **fork** are not granted `id-token: write` by default, so forks cannot obtain this role — but
if fork PRs are ever enabled, revisit this condition.

### 3.5 The constraint that shapes the workflow

Bitbucket authenticates *before* the container starts, so the pipeline can run its steps
directly inside the ECR image. GitHub Actions cannot: `jobs.<id>.container` is pulled before
any step runs, and there is no OIDC hook at that point. Registry credentials for a job
container must come from `container.credentials`, which needs a username and password — not
OIDC.

| Option | How | Verdict |
|---|---|---|
| **A. Pull manually, run via `docker`** | authenticate with OIDC, `docker pull`, then `docker run` | **Recommended** — keeps the exact pinned image, no secrets |
| **B. `container:` with credentials** | store an ECR password as a secret | Rejected — reintroduces a stored secret |
| **C. Build the image in the workflow** | `docker build` from the Dockerfile | **Not viable** — breaks two tests (**F5**) |

Option C is the intuitive choice and it does not work. Two tests in
`tests/processors/test_pdfjam_processor.py` assert byte-identical PDF output against committed
fixtures (4178 and 4038 bytes). A freshly built image ships TeX Live 2025/dev and produces
different byte counts; both fail. Reproduced locally: 13 passed, 2 failed. CI passes today
precisely because it pulls the pinned ECR image.

### 3.6 Required AWS changes

Only one role. No provider, no secrets.

**Permissions policy** — `GithubActionsEcrPull-microservice-pdftransformation`, scoped to the
one repository in the correct region:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "GetAuthorizationToken",
      "Effect": "Allow",
      "Action": ["ecr:GetAuthorizationToken"],
      "Resource": "*"
    },
    {
      "Sid": "PullThisRepositoryOnly",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer"
      ],
      "Resource": "arn:aws:ecr:eu-west-1:397662812780:repository/microservice-pdftransformation"
    }
  ]
}
```

`ecr:GetAuthorizationToken` must stay on `Resource: "*"` — it is account-level and cannot be
resource-scoped. The rest is the minimum for `docker pull`; the `Describe*` / `ListImages`
actions in the current Bitbucket policy are not needed.

**Role** — `GithubActionsOidc-microservice-pdf-transformation`, trust policy per §3.4,
`maxSessionDuration` 3600s to match `OidcRole` in `bitbucket-pipelines-auth`.

**Where it should live.** `bitbucket-pipelines-auth` already owns this shape of resource. A
`GithubOidcRole` construct alongside `OidcRole`, plus a stack under `lib/stacks/repos/`, would
follow the existing pattern and keep roles under version control.

Its four-step onboarding process maps onto GitHub and gets *simpler*:

| Bitbucket onboarding step | GitHub equivalent |
|---|---|
| 1. Look up the repository UUID and add it to `bin/…` | **not needed** — no UUID in the claim |
| 2. Create a stack in `lib/stacks/repos/<repo>/` | same |
| 3. Reference the stack with the target account's `env` | same |
| 4. Add an `OidcProviderStack` if the account lacks a provider | **not needed** — provider already exists (§3.2) |

So onboarding a GitHub repo is steps 2 and 3 only. The managed path is now *shorter* than the
manual one — a second argument for CDK. Doing it by hand would repeat the mistake behind **F1**.
**This is a decision for @navid.ghanian**; the recommendation is CDK.

### 3.7 Environments and secrets

This repo needs **neither**. It has no `deployment:` blocks and no repository variables; the
account ID, role ARN and region are hardcoded (**F2**). The migrated workflow keeps them
hardcoded, so there is nothing to create in GitHub.

For repos that *do* use them:

| Bitbucket | GitHub | Notes |
|---|---|---|
| Deployment environment (`deployment: staging`) | Environment | GitHub adds required reviewers and wait timers, which Bitbucket lacks |
| Deployment variable | Environment secret / variable | scoped to that environment only |
| Repository variable | Repository secret / variable | available to all workflows |
| Secured variable | Secret | masked in logs in both |

The useful gain: a GitHub environment can be referenced in the trust policy
(`...:environment:production`), so AWS itself can enforce that only the production environment
assumes the production role. Bitbucket's `sub` cannot express the deployment environment.

---

## 4. Side by side

| | Bitbucket Pipelines (today) | GitHub Actions (target) |
|---|---|---|
| Opt-in | `oidc: true` on the step | `permissions: id-token: write` |
| Token | `$BITBUCKET_STEP_OIDC_TOKEN` | requested by the credentials action |
| Issuer | `api.bitbucket.org/2.0/workspaces/expertinfo/pipelines-config/identity/oidc` | `token.actions.githubusercontent.com` |
| `sub` claim | `{repository-uuid}:{step-uuid}` | `repo:Paligo/<repo>:<ref-or-context>` |
| `aud` claim | `ari:cloud:bitbucket::workspace/<uuid>` | `sts.amazonaws.com` |
| Repo identified by | opaque UUID | human-readable path |
| Exchange performed by | runner (declarative) or script (manual) | `aws-actions/configure-aws-credentials` |
| Image authentication | **before** the container starts | not possible for `container:` — pull inside the job |
| Max session | 1 hour | 1 hour |
| Role naming | `BitbucketPipelinesOidc-<repo>` | none yet — proposed in §3.6 |
| Secret scoping | deployment environments, repository variables | Environments, environment secrets |

One reviewer-facing gain: Bitbucket's UUID-based `sub` cannot be audited without
cross-referencing the registry in `bitbucket-pipelines-auth`. GitHub's names the org and repo
directly, so trust policies become self-documenting.

---

## 5. The translated workflow

Proposed `.github/workflows/tests.yml`. **Not committed** — this repo is not migrating yet, and
a live workflow file would run the moment the repo landed on GitHub.

```yaml
name: Tests

on:
  pull_request:
  workflow_dispatch:      # equivalent of Bitbucket's `custom:` manual trigger

permissions:
  id-token: write         # mandatory — without it the OIDC token cannot be requested
  contents: read

env:
  AWS_REGION: eu-west-1
  ECR_REGISTRY: 397662812780.dkr.ecr.eu-west-1.amazonaws.com
  IMAGE: microservice-pdftransformation:latest

jobs:
  pytest:
    name: Run tests
    runs-on: ubuntu-24.04-arm     # must be arm64 — see notes
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials via OIDC
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::397662812780:role/GithubActionsOidc-microservice-pdf-transformation
          aws-region: ${{ env.AWS_REGION }}

      - name: Log in to ECR
        uses: aws-actions/amazon-ecr-login@v2

      - name: Pull the pinned test image
        run: docker pull "$ECR_REGISTRY/$IMAGE"

      - name: Run pytest
        run: |
          docker run --rm \
            -v "$PWD/src:/function/src" \
            -v "$PWD/tests:/function/tests" \
            --entrypoint "" \
            "$ECR_REGISTRY/$IMAGE" \
            sh -c "poetry install && poetry run pytest tests --disable-warnings"
```

### Four things that are easy to get wrong

**`--entrypoint ""` is required.** The image's `ENTRYPOINT` is
`poetry run python -m awslambdaric` (the Lambda runtime client). Without overriding it, the
container starts the Lambda runtime instead of pytest. Bitbucket replaces the entrypoint itself
for step images, so this is invisible today.

**The runner must be arm64.** The image is built `--platform linux/arm64` and today's pipeline
declares `runtime.cloud.arch: arm`. On an x86 runner, `docker run` of an arm64 image either
fails or falls back to QEMU emulation — slow, and a poor place to be running byte-exactness
assertions. `ubuntu-24.04-arm` is free for public repos; **for private repos arm runners depend
on the GitHub plan**, so confirm availability. If unavailable, that is a blocker to raise, not
something to work around with emulation.

**Mounting `src` and `tests` mirrors local development.** The `Makefile` does the same. It means
the workflow tests the checked-out code rather than the code baked into the image, which is what
Bitbucket gives you by cloning into the container.

**No secrets are referenced, deliberately.** The account ID, registry and role ARN are
hardcoded, exactly as in `bitbucket-pipelines.yml` today. None are sensitive, and it preserves
the property that this repo stores nothing in CI settings.

---

## 6. Migration runbook

Migration of `expertinfo/microservice-pdf-transformation` (Bitbucket) to
`Paligo/microservice-pdf-transformation` (GitHub).

| Item | Value |
|---|---|
| Source | `git@bitbucket.org:expertinfo/microservice-pdf-transformation.git` |
| Target | `git@github.com:Paligo/microservice-pdf-transformation.git` |
| Tracked files | 52 |
| Branches | 4 (`main` + 3 feature/hotfix) |
| Tags | 0 |
| Submodules / Git LFS | none |
| Bitbucket secrets / deployment variables | none (**F2**) |
| Production deploy pipeline | none |

### Pre-flight

**P1. Confirm the target org.** `Paligo` — evidenced by the existing role's trust policy
(§3.2). `github.com/expertinfo` also exists but has 0 repositories. Confirm with
@navid.ghanian before creating anything.

**P2. Confirm the `@paligo/retention` team exists in the GitHub org.** `CODEOWNERS` already
uses GitHub syntax (`* @paligo/retention`) for Aikido routing. If the team does not exist, the
file is silently inert — no error, no reviewers assigned. Verify it exists and has write access.

**P3. Inventory open pull requests.**
```
https://bitbucket.org/expertinfo/microservice-pdf-transformation/pull-requests/
```
Pull requests do **not** transfer. Branches and commits do; PR metadata (description, comments,
review approvals, linked Jira issues) does not. Record source branch, target branch, author and
Jira key for each.

Candidate branches:
- `PAL2-11926-pdf-transformation-tests-are-not-working-if-container-is-not-running`
- `PAS-527-cdk-for-microservice`
- `hotfix/PAL2-11910-errors-emitted-from-pdf-service`

`PAL2-11926` concerns test fragility that reproduces locally (**F5**). Read it before cutover —
it may already contain the fix.

**P4. Decide the PR strategy.** Either merge/close all open PRs before cutover (preferred), or
re-create them manually on GitHub afterwards with the original description and a link to the
archived Bitbucket PR.

**P5. Announce a freeze window.** No pushes to Bitbucket between step 1 and step 6. The repo is
small, so minutes, not hours.

**P6. Take a local safety mirror.** This is the rollback artefact.
```bash
git clone --mirror git@bitbucket.org:expertinfo/microservice-pdf-transformation.git \
  ./pdftransformation-backup.git
```
Keep it until the migration is signed off.

### Cutover

**1. Create the empty GitHub repo.** `github.com/organizations/Paligo/repositories/new` → name
`microservice-pdf-transformation`, **Private**, and **no** README, `.gitignore`, or licence. Any
initial commit creates a divergent history that blocks the mirror push.

**2. Mirror the repository.**
```bash
git clone --mirror git@bitbucket.org:expertinfo/microservice-pdf-transformation.git
cd microservice-pdf-transformation.git
git push --mirror git@github.com:Paligo/microservice-pdf-transformation.git
```
`--mirror` transfers all branches, tags and refs, and preserves commit SHAs.

**3. Verify the mirror.** Do not proceed on a successful exit code alone — compare refs.
```bash
git ls-remote --heads git@bitbucket.org:expertinfo/microservice-pdf-transformation.git | sort > /tmp/bb.txt
git ls-remote --heads git@github.com:Paligo/microservice-pdf-transformation.git   | sort > /tmp/gh.txt
diff /tmp/bb.txt /tmp/gh.txt && echo "branches + SHAs identical"
```
Expect 4 branches, 0 tags, identical SHAs. Any difference stops the migration.

**4. Recreate repository settings.** None of this transfers.

| Setting | Action |
|---|---|
| Default branch | set to `main` |
| Branch protection on `main` | require PR before merge; require 1 approval; require status checks |
| Required status check | `Run tests` — **add only after step 5**, or merges block on a check that has never run |
| `CODEOWNERS` | already in the repo; confirm P2 and enable "Require review from Code Owners" |
| Access | grant `@paligo/retention` write; match the Bitbucket permission set |
| Merge strategy | match the Bitbucket setting (squash / merge commit) |
| Aikido | re-point the scanner at the GitHub repo |

**5. Add the GitHub Actions workflow.** Requires the IAM role from §3.6 to exist first. The
workflow must **pull the existing ECR image** rather than build one (**F5**). Open a PR with
`.github/workflows/tests.yml` and confirm it passes on that PR before making the check required.

**6. Update references to the Bitbucket URL.**

`cdk/lib/cdk-stack.ts:19` and `cdk/lib/cdk-stack-v2.ts:29` both hardcode:
```typescript
cdk.Tags.of(this).add('paligo:repository',
  'https://bitbucket.org/expertinfo/microservice-pdf-transformation/src/main/');
```
Changing the tag value causes CDK to update tags on every tagged resource in the stack, so treat
it as its own reviewed change with a `cdk diff` — not a drive-by edit during cutover.

**Blocker: how these stacks are deployed today is not documented.** `cdk/bin/cdk.ts` defines two
stacks — `lambda-microservice-pdf` (`CdkStack`) and `PaligoLambdaPdfTransform-V2` (`CdkStackV2`)
— both taking account and region from `CDK_DEFAULT_ACCOUNT` / `CDK_DEFAULT_REGION`. The README
documents only the LocalStack setup, and `bitbucket-pipelines.yml` contains no deploy step, so
deployment is presumably manual from a developer machine.

This step therefore cannot be written precisely yet. Establish first:
- which of the two stacks is live (both? is V2 a replacement?)
- who deploys, from where, with which profile
- whether `cdk diff` is clean today — if the deployed state has drifted, the tag change will
  surface unrelated differences and cannot be reviewed safely

Until that is known, treat step 6 as "raise a follow-up ticket", not an executable step. Nothing
else depends on it — the tag is metadata, and cutover completes fine with the old value.

Also update: README links, Confluence pages referencing the Bitbucket URL, Jira automation or
dashboards, and any Slack integrations.

**7. Developers re-point their remotes.**
```bash
cd microservice-pdf-transformation
git remote set-url origin git@github.com:Paligo/microservice-pdf-transformation.git
git remote -v
git fetch --all
```
No re-clone needed — SHAs are preserved, so existing local branches stay valid. Anyone with
unpushed work should push to Bitbucket *before* the freeze, or to GitHub after.

**8. Make the Bitbucket repo read-only. Do not delete it.** In Repository settings:
- remove write access for all users, keep read access
- set the description to `MIGRATED → github.com/Paligo/microservice-pdf-transformation`
- disable pipelines, so the old pipeline cannot run and confuse anyone

Retain it as the record of PR history and review discussion, which did not transfer. Deleting it
destroys that permanently.

**9. Post-cutover verification.**
- [ ] `git clone` from GitHub succeeds, `main` matches the pre-migration SHA
- [ ] all 4 branches present
- [ ] workflow runs green on a test PR
- [ ] the workflow's `aws sts get-caller-identity` shows the expected assumed role
- [ ] branch protection blocks a direct push to `main`
- [ ] `CODEOWNERS` assigns `@paligo/retention` as reviewer on a test PR
- [ ] Bitbucket repo is read-only and pipelines disabled
- [ ] Aikido reports against the GitHub repo

### Rollback

Cheap, because Bitbucket is retained read-only rather than deleted, and no production deploy
path is involved.

**Trigger:** mirror verification fails (step 3), the workflow cannot authenticate to AWS
(step 5), or a blocking problem is found within the sign-off window.

1. Announce the rollback; stop all pushes to GitHub.
2. Restore write access on the Bitbucket repo and re-enable its pipelines (reverses step 8).
3. Developers re-point back:
   ```bash
   git remote set-url origin git@bitbucket.org:expertinfo/microservice-pdf-transformation.git
   ```
4. If any commits landed on GitHub after cutover, push them back:
   ```bash
   git push git@bitbucket.org:expertinfo/microservice-pdf-transformation.git --all
   ```
5. Revert the `paligo:repository` CDK tag change if step 6 was deployed, and `cdk deploy`.
6. Delete or rename the GitHub repo to avoid ambiguity about which is authoritative.
7. Leave the IAM role in place — it is inert without a workflow, and avoids redoing §3.6.

**Point of no return:** none within the freeze window. After developers have pushed new work to
GitHub for more than a day, rollback means merging divergent history rather than discarding it.
Sign off within one working day.

---

## 7. Findings

**F1 — This repo's Bitbucket role is unmanaged.**
`microservice-pdf-transformation` is not one of the seven onboarded repositories: it does not
appear in `repositoryUuids` in `bin/bitbucket-pipelines-auth.ts`, and has no stack under
`lib/stacks/repos/`. Its role is `bitbucket_pipeline_pdftransformation` (snake_case, not
`BitbucketPipelinesOidc-*`) with a hand-written inline policy. Compare
`microservice-contentoutput`, whose policy carries the CDK-generated name
`BitbucketPipelinesOidcmicroservicecontentoutputDefaultPolicy7D75D228`.

Consequences: there is no CDK definition to update during migration, so the GitHub role is a
clean build — but this repo is therefore **not representative** as a migration template. Every
other repo's role is CDK-managed, so their migration means editing `bitbucket-pipelines-auth`,
which this exercise will not exercise. Worth raising before this plan is adopted as *the*
template.

**F2 — No Bitbucket secrets or deployment variables exist.**
No `deployment:` blocks, no repository variables. Account ID, role ARN and region are hardcoded
in the YAML. (`microservice-contentoutput` by contrast uses `deployment: staging`.) Nothing needs
migrating into GitHub Environments or secrets — the main reason this repo is cheap to migrate.

**F3 — Trust policies org-wide omit the `aud` condition.**
Neither this role nor the CDK-generated ones constrain `aud`; only `sub` is checked. Provider
registration is workspace-scoped so exposure is bounded, but adding `aud` would be defence in
depth. This is the org-wide pattern rather than a defect specific to this repo, so any change
belongs in `bitbucket-pipelines-auth`.

**F4 — `Resource: "*"` on the ECR policy.**
`bitbucket-ecr-access-all` grants its ECR read actions on all repositories rather than just
`microservice-pdftransformation`. The GitHub equivalent should scope to the single repository ARN
rather than copy the wildcard (done in §3.6).

**F5 — CI depends on the pinned ECR image, not a fresh build.**
The pipeline pulls `microservice-pdftransformation:latest` from ECR. Two tests in
`tests/processors/test_pdfjam_processor.py` assert byte-identical output against committed
fixtures (4178 and 4038 bytes). A locally built image ships TeX Live 2025/dev and produces
different byte counts, so those tests fail on a fresh build while passing in CI. The GitHub
workflow **must keep pulling the same ECR image**.

**F6 — The existing GitHub role's ECR policy is scoped to an empty region.**
`bitbucket-pipelines-ecr-access` (v1) scopes its pull actions to
`arn:aws:ecr:us-west-1:397662812780:repository/*`. Verified against the account:

| Region | ECR repositories |
|---|---|
| `eu-west-1` | 36 (including `microservice-pdftransformation` and `paligo/app`) |
| `us-west-1` | **0** |

So `ReadRepositoryContents` applies to an empty region and grants nothing. The role can call
`GetAuthorizationToken` but cannot fetch a manifest or layer from any real repository.
`AmazonElasticContainerRegistryPublicReadOnly` does not compensate — that covers ECR *Public*,
not this private registry. The `github-actions` role therefore **cannot pull from private ECR**.
Either `Paligo/paligo-app` does not pull from private ECR, or that path is silently failing —
possibly a live bug rather than a curiosity.

**F7 — The existing GitHub role trusts a bare wildcard.**
`repo:Paligo/paligo-app:*` matches every branch, tag, pull request and environment, so anyone
who can push a branch can assume it. The Bitbucket roles are tighter: `{repo-uuid}:*` wildcards
only the *step* UUID within one repository, not the git ref. Do not copy this shape.

F6 and F7 concern a repository outside this ticket's scope and are IAM-posture questions rather
than technical blockers. Raise with @navid.ghanian and in `#ask-security`.

---

## 8. Related work already in flight

Raised by Jakob Sisk on the ticket; verified against the code and the staging account.

**`cdk-runner`** — a generic image that performs the OIDC bootstrap and runs `cdk diff` /
`cdk deploy` for any repo's CDK app, configured entirely through environment variables. It
re-issues credentials per account/region so a multi-region deploy cannot expire mid-run on the
1-hour session. Published as `paligo/cdk-runner` in eu-west-1 staging — tags `0`, `0.1.0`,
`latest`, last pushed 2026-07-09 (confirmed via `ecr describe-images`).

This repo would fit it as a consumer without modification: `cdk/bin/cdk.ts` takes account and
region from `CDK_DEFAULT_ACCOUNT` / `CDK_DEFAULT_REGION`, and `cdk/package.json` carries
`aws-cdk` 2.1135.0, `aws-cdk-lib` ^2.260.0 and `ts-node` in devDependencies — which is what
`cdk-runner` expects.

Three open, unassigned tickets under PAS-1419 (epic PAS-1482) overlap:

| Ticket | Overlap |
|---|---|
| PAS-2613 — migrate `infra-base-internal-services` to `cdk-runner` | No repo consumes the image yet, so it is published but **unproven in a real pipeline**. Any plan assuming it works is assuming something untested. |
| PAS-2617 — document `cdk-runner` and its variable interface | The variable interface is the integration surface; undocumented, it cannot be relied on in a runbook. |
| PAS-2618 — make `bitbucket-pipelines-auth` onboarding config-driven | Directly overlaps the proposed `GithubOidcRole`. Adding a second hand-authored pattern is work PAS-2618 would then have to absorb. |

`infra-base-internal-services` is worth reading as the working end-to-end example: its PR
pipeline runs `cdk diff` and posts the result as a PR comment, and deploy is a manual
`custom: deploy` pipeline rather than automatic on merge. That shape — diff on PR, deploy on
demand — is a reasonable target for this repo too, but it is a separate ticket.

---

## 9. Decisions blocking execution

1. **Where the IAM role lives** — a `GithubOidcRole` construct in `bitbucket-pipelines-auth`
   (recommended, matches the existing pattern) or hand-created. Hand-creating repeats the
   mistake behind **F1**.
2. **arm64 runner availability** for private repos on Paligo's GitHub plan (§5).
3. **Open PR strategy** — drain before cutover, or re-create on GitHub (P3/P4).
4. **Confirm the target org is `Paligo`** — strongly evidenced by the existing role's trust
   policy, but `github.com/expertinfo` also exists.
5. **Sequencing against PAS-2618** — whether the `GithubOidcRole` construct waits for
   config-driven onboarding or lands before it.
6. **How this repo's two CDK stacks are deployed today** — blocks runbook step 6, and is worth
   establishing regardless of the migration.

### Other open items

- Repository/deployment variable inventory was confirmed by reading the YAML only. The Bitbucket
  repo-settings UI should be checked to confirm no unused variables are defined.
- The repository UUID `4fac6a60-c04b-46f7-9a50-6dff6b94d23f` in the trust policy was read from
  IAM; cross-check it against the Bitbucket repo UUID in the UI or API.
- Whether Aikido re-pointing needs a separate ticket or admin access.

---

## 10. Local environment issues

Not part of the migration, but found while getting the service running. Worth a small follow-up
PR.

| Issue | Detail |
|---|---|
| `make setup` creates the wrong bucket | creates `microservice-pdf`; `src/services/file_service.py:18-19` reads `microservice-inbound` and writes `microservice-outbound` |
| `make request-*` payloads are stale | `src/main.py:19` requires a `path` key, and line 31 requires `body` to be a JSON **string**, not an object |
| README LocalStack instructions broken | the `localstack/localstack` image now requires a licence token; a pinned tag such as `:3.8` works |
| README omits the container DNS alias | the Lambda reaches LocalStack at `localstack.container:4566`, so the container needs that network alias |
| `paligo_backend` network is assumed | not created by any documented step |

With those worked around, the service runs correctly end to end: the `/status` health check
returns 200, and a crop job downloads `sample.pdf` from S3, transforms it, and uploads the
result to the outbound bucket.

---

## Sources

| Source | Location |
|---|---|
| Pipeline definition | `bitbucket-pipelines.yml` |
| Comparison: pattern B | `microservice-contentoutput/bitbucket-pipelines.yml:132-160` |
| Comparison: pattern C | `paligo-cli/bitbucket-pipelines.yml:58-78` |
| Role provisioning | `bitbucket-pipelines-auth/lib/constructs/oidc-role.ts` |
| Account and UUID registry | `bitbucket-pipelines-auth/bin/bitbucket-pipelines-auth.ts` |
| Onboarding process | `bitbucket-pipelines-auth/README.md` |
| IAM, ECR (live) | accounts 397662812780 and 230763337748 |
