# Deploy Guide

## 0. Prerequisites

1. **Terraform** >= 1.5 - https://developer.hashicorp.com/terraform/install
2. **AWS CLI** configured with credentials that can create IAM roles,
   S3 buckets, DynamoDB tables, Elastic Beanstalk apps/environments,
   and Cognito user pools:
   ```bash
   aws configure
   aws sts get-caller-identity   # sanity check
   ```
3. **Bedrock model access** for the model in `terraform/variables.tf`
   (`bedrock_model_id`, default `global.anthropic.claude-haiku-4-5-20251001-v1:0`):
   - `bedrock_model_id` must be an **inference profile id** (`global.*` or
     `au.*`), not a bare foundation-model id (e.g.
     `anthropic.claude-opus-4-6-v1` is rejected by Converse with
     `ValidationException`). Local development uses
     `au.anthropic.claude-opus-4-6-v1` (set in `setup_aws_env.ps1` /
     `bedrock_service.py`); the Beanstalk stack's env var comes from
     `var.bedrock_model_id`, so set it to a profile id you have access to.
   - Bedrock foundation models are auto-enabled in commercial regions on
     first use. Verify with:
     ```bash
     aws bedrock list-foundation-models --region us-east-1 \
       --query "modelSummaries[?contains(providerName,'Anthropic')].[modelId,modelLifecycle.status]" \
       --output table
     ```
   - If your AWS account is brand new, Bedrock/Textract/Translate may
     return `SubscriptionRequiredException` until the account is fully
     activated (payment method + identity verification). The app still
     runs via the offline rules-engine fallback either way.
4. Default region is `us-east-1` (broadest Bedrock model availability).
   Set `aws_profile` in `terraform.tfvars` to match your AWS CLI profile
   (`"personal"` or `"default"`).

## 1. Deploy

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars if you want a different region/instance size

terraform init
terraform plan     # review what will be created
terraform apply    # type "yes" to confirm
```

What happens:
1. Terraform zips the `../app` folder into `terraform/build/app.zip`.
2. Uploads it to a new S3 bucket.
3. Creates the Elastic Beanstalk application + application version
   pointing at that zip.
4. Creates the Elastic Beanstalk **environment** (this is the slow
   step - it's provisioning an ALB, an Auto Scaling Group, and EC2
   instances, then running your app under gunicorn behind nginx).
5. Creates the S3 uploads bucket, DynamoDB table, IAM roles, and
   Cognito user pool.

`terraform apply` returns once the *API calls* to create everything
have succeeded - the Beanstalk environment itself can take a few more
minutes to finish booting. Check status with:

```bash
terraform output eb_environment_name
aws elasticbeanstalk describe-environments \
  --environment-names <the name from above> \
  --query "Environments[0].{Status:Status,Health:Health}"
```

Wait until `Status` is `Ready` and `Health` is `Green` (or `Ok`,
depending on CLI version).

## 2. Test in the UI

```bash
terraform output app_url
```

Open that URL in a browser. Then:

1. Click **"Load Sample Menu"** - runs all 16 sample dishes through
   OCR-skip -> Bedrock allergen extraction -> FSANZ rules-engine
   verification -> 4-language translation -> DynamoDB save. This is
   the fastest way to confirm the whole pipeline actually works end to
   end in your AWS account.
2. Switch the **"Display language"** dropdown (top right) - dish
   names/descriptions switch to the Bedrock-translated text.
3. Tick the **Gluten-Free / Dairy-Free / Vegan** filter checkboxes -
   the grid filters live.
4. Click any dish card - the review modal shows whether the Bedrock
   LLM and the deterministic rules engine agreed, and lets you
   override the confirmed allergen list (human-in-the-loop) or delete
   the dish.
5. Try **"Upload a menu file"** with a photo of a real menu (JPG/PNG)
   to exercise the Textract OCR path, or **"Add a dish manually"** to
   test a single description without a file.

## 3. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `app_url` returns 502/503 | Environment is still booting - wait, then re-check `describe-environments` health. If it stays unhealthy, check `aws elasticbeanstalk describe-events --environment-name <name> --max-records 20` for the actual error. |
| "Load Sample Menu" works but every dish shows `"llm_source": "offline"` | Bedrock model access hasn't been granted yet in this region/account (step 0.3), or `bedrock_model_id` in `terraform.tfvars` doesn't match a model you have access to. The app *keeps working* via the offline fallback either way. |
| RAG falls back to local with `Incompatible configuration: vectorSearchConfiguration is not supported for managed knowledge bases` | `boto3` is too old to know `managedSearchConfiguration`. Install the pinned version from `app/requirements.txt` (`boto3==1.43.88` or newer, ≥1.36) into whatever environment runs the code. |
| Dish stores `rag_engine=local-rag + rules` even in real AWS mode | The record was created *before* the RAG fix was applied. Re-run "Load Sample Menu" (or re-add the dish) to regenerate with AWS RAG; new dishes use `bedrock-rag + rules`. |
| Translations look like `[Spanish - offline] ...` | Same Bedrock access issue as above, and Amazon Translate fallback also failed (check the instance role has `translate:TranslateText`, already granted in `iam.tf`). |
| `terraform apply` fails with an IAM permissions error | Your AWS CLI credentials don't have rights to create IAM roles/policies. Ask your AWS admin for `IAMFullAccess`-equivalent rights, or have them run this for you. |
| `terraform apply` fails on the solution stack data source (`no matching Elastic Beanstalk Solution Stack found`) | AWS periodically retires old Python 3.12 platform versions. Loosen `python_version_regex` in `terraform.tfvars` to `^64bit Amazon Linux 2023.*Python 3\\.1[0-9]$` or check `aws elasticbeanstalk list-available-solution-stacks` for exact current names. |

This replaces the failure mode you were hitting with Amplify (opaque
build failures with "no proper issue identified") with a stack where
every layer - the zip, the IAM role, the environment variables, the
health check path - is explicit in Terraform and inspectable with
`aws elasticbeanstalk describe-events`.

## 4. Updating the app after a code change

Any change under `app/` changes the zip's MD5 hash, which Terraform
uses in the application version name - so a normal `terraform apply`
picks it up and deploys the new version automatically. No manual `eb
deploy` step needed.

## 5. Destroying everything

```bash
cd terraform
terraform destroy
```

Confirm with `yes`. This removes the Beanstalk environment/app, both
S3 buckets (even though they contain the uploaded zip / raw menu
files, thanks to `force_destroy = true`), the DynamoDB table, the IAM
roles/policies, and the Cognito user pool - nothing is left behind and
nothing needs a manual "empty bucket first" step.
