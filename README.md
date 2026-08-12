# AI-Powered Allergen Compliance & Menu Translation - Beanstalk Edition

This is a from-scratch rebuild of the project in `AI_Allergen_Compliance_Presentation.pdf`, hosted on Elastic Beanstalk (per your request) and removing the Bedrock knowledge-base / RAG component - compliance verification is done with a deterministic rules engine instead.

Everything is provisioned with Terraform and is fully tear-down-able with `terraform destroy` (see "Destroying everything" below).

## Allergen source of truth

The mandatory declarable allergen list is taken from the NZ MPI official page
[Allergen declarations, warnings and advisory statements on food labels](https://www.mpi.govt.nz/food-business/labelling-composition-food-drinks/allergen-declarations-warnings-and-advisory-statements-on-food-labels):

> peanuts, almonds, Brazil nuts, cashews, hazelnuts, macadamias, pecans, pine nuts, pistachios, walnuts, crustacean, **molluscs**, fish, milk, egg, wheat, soy, sesame, lupin.

Plus: gluten (from wheat, rye, barley, oats, spelt, triticale) must also be listed, and added sulphites only when above 10 mg/kg. Each individual tree nut and cereal must be declared separately. These categories are implemented in `app/services/allergen_rules.py` (PEAL_CATEGORIES).

## What actually runs where

| PDF architecture item | This build |
|---|---|
| Application hosting | Elastic Beanstalk, provisioned by Terraform |
| API Gateway + Cognito auth | Not required - Beanstalk's own load balancer serves the app directly. A Cognito User Pool is still provisioned (`terraform/cognito.tf`) to cover that checklist item for later use, but the demo UI does not enforce login yet |
| Lambda two-step chain (Analyze -> Translate) | Runs as two plain function calls inside one Flask request (`app/application.py: _run_pipeline`) - no Lambda needed once the app has its own always-on compute (Beanstalk) |
| Bedrock LLM anchored on NZ MPI PEAL knowledge base | Allergens are extracted by a Bedrock LLM call and cross-checked by a deterministic keyword rules engine (`app/services/allergen_rules.py`) built directly from the NZ MPI mandatory declarable allergen list (see "Allergen source of truth"). The union of both is what's shown as "Contains X"; disagreements are flagged for human review |
| AWS Textract OCR | `app/services/textract_service.py` - only invoked when a file is uploaded |
| Multilingual translation (Spanish, German, Japanese, Mandarin) | `app/services/bedrock_service.py::translate_dish` - Bedrock LLM primary, Amazon Translate as an automatic fallback if Bedrock fails |
| DynamoDB (menus & allergen metadata) | `terraform/dynamodb.tf` + `app/services/dynamo_service.py` |
| S3 (raw menu files) | `terraform/s3.tf` + `app/services/s3_service.py` |
| Human-in-the-loop review | Click any dish card in the UI -> checkbox override of confirmed allergens -> `PATCH /api/menus/<id>/items/<id>` |

## Repo layout

```
app/                    Flask application (this whole folder is what gets
                         zipped and deployed to Elastic Beanstalk)
  application.py         Routes + the two-step pipeline
  services/
    allergen_rules.py     FSANZ 1.2.3 rules engine (no KB/RAG)
    bedrock_service.py     Bedrock allergen extraction + translation
    textract_service.py    OCR
    dynamo_service.py      DynamoDB CRUD (+ local JSON fallback)
    s3_service.py           Raw file storage (+ local fallback)
  static/                 UI (index.html / style.css / app.js)
  sample_data/
    sample_menu.json        8 sample dishes used by "Load Sample Menu"
  requirements.txt
  Procfile                gunicorn entry point Beanstalk uses

terraform/              All infrastructure, Beanstalk included
  beanstalk.tf            Zips app/, uploads it, creates the EB app/env
  s3.tf                    2 buckets (uploads + EB app version bundles),
                           both force_destroy = true
  dynamodb.tf              Menu items table, deletion_protection disabled
  iam.tf                   EC2 instance role (Bedrock/Textract/S3/Dynamo/
                           Translate) + EB service role
  cognito.tf               User pool (provisioned, not yet wired into UI)
  variables.tf / outputs.tf / providers.tf / main.tf

run_local.sh            Runs the Flask app locally with LOCAL_MODE=true -
                         no AWS account needed, everything AWS-shaped is
                         stubbed so you can click through the UI first.
```

## AWS credentials setup (required before `terraform apply`)

Terraform needs valid AWS credentials on the machine you're running it from, and that identity needs enough IAM permission to create the resources listed above (Elastic Beanstalk, S3, DynamoDB, IAM roles, Cognito). Do this once, before the "Quick start" steps below.

### 1. Install the AWS CLI

```
# macOS
brew install awscli

# Linux
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip && sudo ./aws/install

# Windows: download the MSI installer from
# https://awscli.amazonaws.com/AWSCLIV2.msi
```

Verify with `aws --version`.

### 2. Get an access key

You need an IAM user (or IAM role) with programmatic access - not your root account.

1. Sign in to the [IAM console](https://console.aws.amazon.com/iam/).
2. Create a new IAM user (or use an existing one) dedicated to this project, e.g. `allergen-compliance-terraform`.
3. Attach permissions. For a quick start you can attach the AWS-managed policies below; for production, replace these with a scoped-down custom policy:
   - `AdministratorAccess` (simplest, broadest - fine for a personal/demo AWS account)
   - or, more scoped: `AmazonS3FullAccess`, `AmazonDynamoDBFullAccess`, `AWSElasticBeanstalkFullAccess`, `IAMFullAccess`, `AmazonCognitoPowerUser`, `AmazonBedrockFullAccess`, `AmazonTextractFullAccess`, `TranslateFullAccess`
4. Under **Security credentials**, create an **access key** (choose "Command Line Interface (CLI)" as the use case). Save the Access Key ID and Secret Access Key somewhere safe - the secret is only shown once.

### 3. Configure the credentials locally

```
aws configure
```

You'll be prompted for:

```
AWS Access Key ID [None]: <paste your access key ID>
AWS Secret Access Key [None]: <paste your secret access key>
Default region name [None]: us-east-1   # or whatever region you'll deploy to
Default output format [None]: json
```

This writes credentials to `~/.aws/credentials` and config to `~/.aws/config`. Terraform's AWS provider (`terraform/providers.tf`) picks these up automatically - no extra Terraform config needed.

Alternatively, instead of `aws configure`, you can export environment variables in the shell you'll run `terraform apply` from:

```
export AWS_ACCESS_KEY_ID="your-access-key-id"
export AWS_SECRET_ACCESS_KEY="your-secret-access-key"
export AWS_DEFAULT_REGION="us-east-1"
```

If you use AWS SSO or an assumed role instead of a long-lived access key, `aws sso login --profile <profile-name>` followed by `export AWS_PROFILE=<profile-name>` works too - Terraform respects `AWS_PROFILE`.

### 4. Verify credentials work

```
aws sts get-caller-identity
```

You should see your account ID, user ARN, and user ID printed back. If this fails, `terraform apply` will fail at the same step, so fix it here first.

### 5. Request Bedrock model access (one-time, per account/region)

Bedrock model access must be explicitly enabled per AWS account and region before it can be invoked:

1. Open the [Bedrock console](https://console.aws.amazon.com/bedrock/) in the region you plan to deploy to.
2. Go to **Model access** in the left sidebar.
3. Request access to the Claude model(s) used by `app/services/bedrock_service.py`.
4. Wait for status to show "Access granted" (usually near-instant for Anthropic models on Bedrock).

With that done, you're ready for the "Quick start" steps below.

## Quick start (real AWS deployment)

See `DEPLOY_GUIDE.md` for the full walkthrough. Short version:

```
cd terraform
cp terraform.tfvars.example terraform.tfvars   # edit region etc. if needed
terraform init
terraform apply
```

Wait for the environment to go "Green"/"Ready" (takes ~4-6 minutes the first time), then open the `app_url` output in a browser and click "Load Sample Menu".

## Testing without any AWS account first

```
./run_local.sh
```

Then open http://localhost:8000. This runs the identical Flask app/UI with Bedrock/Textract/S3/DynamoDB replaced by clearly-labelled offline stubs (still runs the real FSANZ rules engine), so you can confirm the UI/flow works before spending anything on AWS.

## Destroying everything

```
cd terraform
terraform destroy
```

Every resource that can normally block a clean teardown has been set up to allow it:

- Both S3 buckets: `force_destroy = true` (deletes non-empty buckets)
- Elastic Beanstalk application: `force_delete = true` (removes all application versions first)
- DynamoDB table: `deletion_protection_enabled = false`

Nothing here uses `prevent_destroy`, so a single `terraform destroy` tears down the whole stack in one pass.
