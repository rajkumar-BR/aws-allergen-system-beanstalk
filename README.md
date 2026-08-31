# AI-Powered Allergen Compliance & Menu Translation — Beanstalk Edition

A restaurant menu system that reads an uploaded menu, detects mandatory allergens against the NZ/AU **FSANZ Standard 1.2.3** (PEAL) list, translates each dish into 4 languages, and lets a kitchen manager review and override the results.

Hosted on **AWS Elastic Beanstalk** (a single always-on Flask app), provisioned entirely with **Terraform**, and fully tear-down-able with one `terraform destroy`.

**Live demo screenshot:** dual-panel UI — upload/management on the left, colourful live menu preview on the right.

---

## Table of Contents

1. [What it does](#what-it-does)
2. [Architecture](#architecture)
3. [Repo layout](#repo-layout)
4. [Prerequisites](#prerequisites)
5. [Run locally first (no AWS needed)](#run-locally-first-no-aws-needed)
6. [Deploy to AWS — step by step](#deploy-to-aws--step-by-step)
7. [Using the app](#using-the-app)
8. [Updating after a code change](#updating-after-a-code-change)
9. [Destroying everything](#destroying-everything)
10. [Troubleshooting](#troubleshooting)

---

## What it does

A cafe manager uploads a weekly menu (PDF / JPG / PNG) or adds a dish manually. The app then:

1. **OCR** — extracts text from the uploaded file with **AWS Textract** (only runs on file upload)
2. **Allergen analysis** — a **Bedrock LLM** reads each dish description and extracts allergens
3. **Compliance verification** — a **deterministic FSANZ 1.2.3 rules engine** cross-checks the LLM result. The union of both is shown as "Contains X"; any disagreement is flagged for human review. (No knowledge base / RAG — the rule list is built directly from the standard.)
4. **Translation** — **Bedrock** translates each dish name + description into **Spanish, German, Japanese, Mandarin**, with **Amazon Translate** as an automatic fallback
5. **Storage** — dishes + allergens + translations saved to **DynamoDB**; raw files saved to **S3**
6. **Human-in-the-loop** — click any dish card to override its confirmed allergens

If Bedrock/Textract/Translate aren't available (new account, no model access, etc.) the app **degrades gracefully** to offline stubs and the deterministic rules engine — it never crashes.

---

## Architecture

```
Browser (dual-panel UI)
        │  HTTP
        ▼
Elastic Beanstalk  ── Application Load Balancer ── EC2 (gunicorn + Flask)
        │
        │  the two-step pipeline runs as two function calls in ONE request
        │  (no Lambda, no API Gateway):
        │
        ├── Step 1  Textract OCR ──► Bedrock allergen extraction ──► FSANZ rules engine
        └── Step 2  Bedrock translate (ES/DE/JA/ZH)  ──► Amazon Translate fallback
        │
        ▼
S3 (raw menu files)   +   DynamoDB (menus, allergens, translations)
Cognito user pool (provisioned; not enforced in the demo UI)
```

| PDF architecture item | This build |
|---|---|
| Application hosting | Elastic Beanstalk, provisioned by Terraform |
| API Gateway + Cognito auth | Beanstalk's ALB serves the app directly. Cognito pool is provisioned (`terraform/cognito.tf`) but not enforced in the demo UI |
| Lambda two-step chain | Two function calls inside one Flask request (`app/application.py::_run_pipeline`) |
| Bedrock + PEAL knowledge base | Bedrock LLM extraction + deterministic FSANZ 1.2.3 rules engine (`app/services/allergen_rules.py`) — **no RAG/KB** |
| AWS Textract OCR | `app/services/textract_service.py` — only on file upload |
| Translation (ES/DE/JA/ZH) | `app/services/bedrock_service.py::translate_dish` — Bedrock primary, Amazon Translate fallback |
| DynamoDB | `terraform/dynamodb.tf` + `app/services/dynamo_service.py` |
| S3 | `terraform/s3.tf` + `app/services/s3_service.py` |
| Human-in-the-loop | Click a dish card → override checkboxes → `PATCH /api/menus/<id>/items/<id>` |

---

## Repo layout

```
app/                          Flask application (this whole folder is deployed to Beanstalk)
  application.py               Routes + the two-step pipeline (_run_pipeline)
  Procfile                     gunicorn entry point Beanstalk uses
  requirements.txt
  .platform/                   nginx proxy timeout override (300s)
  services/
    allergen_rules.py           FSANZ 1.2.3 rules engine (no KB/RAG)
    bedrock_service.py          Bedrock allergen extraction + translation (+ fallbacks)
    textract_service.py         OCR
    dynamo_service.py           DynamoDB CRUD (+ local JSON fallback)
    s3_service.py               Raw file storage (+ local fallback)
  static/                      UI — index.html / style.css / app.js (colourful dish cards)
  sample_data/
    sample_menu.json            16 sample dishes used by "Load Sample Menu"

terraform/                    All infrastructure, Beanstalk included
  providers.tf                 AWS provider + region + profile
  variables.tf                 region, profile, instance size, model id, etc.
  main.tf                      locals + caller identity
  network.tf                   default VPC/subnets (filtered to AZs that offer the instance type)
  beanstalk.tf                 zips app/, uploads it, creates EB app/env + ALB idle timeout
  s3.tf                        2 buckets (uploads + EB app versions), force_destroy = true
  dynamodb.tf                  menu items table, deletion protection off
  iam.tf                       EC2 instance role (Bedrock/Textract/S3/Dynamo/Translate) + EB service role
  cognito.tf                   user pool (provisioned, not enforced)
  outputs.tf                   prints app_url and next steps
  terraform.tfvars.example     copy to terraform.tfvars

run_local.sh                  Run the Flask app locally with offline stubs (no AWS needed)
DEPLOY_GUIDE.md               Condensed deploy walkthrough (this README is the full version)
```

---

## Prerequisites

| Tool | Install | Check |
|---|---|---|
| **Terraform** ≥ 1.5 | `brew install terraform` or [terraform install](https://developer.hashicorp.com/terraform/install) | `terraform version` |
| **AWS CLI** v2 | `brew install awscli` or [aws cli](https://aws.amazon.com/cli/) | `aws --version` |
| **Python** ≥ 3.11 | `brew install python` | `python3 --version` |

### AWS credentials

You need AWS credentials with permission to create IAM roles, S3, DynamoDB, Elastic Beanstalk, and Cognito.

```bash
aws configure --profile personal
# AWS Access Key ID:     <your key>
# AWS Secret Access Key: <your secret>
# Default region name:   us-east-1
# Default output format: json

aws sts get-caller-identity --profile personal   # verify — should print your account ID
```

> This project's `terraform.tfvars.example` uses `aws_profile = "personal"`. If you configured credentials without a named profile, set `aws_profile = "default"` in your `terraform.tfvars`.

### Bedrock model access (for full AI output)

Bedrock foundation models are auto-enabled in commercial regions on first use. Verify Claude Haiku 4.5 is available:

```bash
aws bedrock list-foundation-models \
  --region us-east-1 \
  --query "modelSummaries[?contains(providerName,'Anthropic')].[modelId,modelLifecycle.status]" \
  --output table
```

- If your AWS account is brand new, **Bedrock, Textract, and Amazon Translate may return `SubscriptionRequiredException`** until the account is fully activated (valid payment method + identity verification). The app still runs — it falls back to the offline rules engine for allergens. Once the account is verified, the AI features light up automatically with no code change.

---

## Run locally first (no AWS needed)

Confirm the UI and pipeline work before spending anything on AWS:

```bash
./run_local.sh
```

Open **http://localhost:8000**. This runs the identical Flask app with Bedrock/Textract/S3/DynamoDB replaced by clearly-labelled offline stubs (the real FSANZ rules engine still runs). Click **Load Sample Menu** to see 16 dishes flow through the pipeline.

---

## Deploy to AWS — step by step

### Step 1 — Configure your variables

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Open `terraform.tfvars` and set your values:

```hcl
aws_region       = "us-east-1"
aws_profile      = "personal"    # or "default"
project_name     = "allergen-demo"
environment      = "dev"
instance_type    = "t3.small"
min_instances    = 1
max_instances    = 2
bedrock_model_id = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
```

> `terraform.tfvars` is git-ignored — it stays on your machine and is never pushed.

### Step 2 — Initialise and review

```bash
terraform init
terraform plan     # review the ~20 resources that will be created
```

### Step 3 — Deploy

```bash
terraform apply    # type "yes" to confirm
```

What happens:
1. Zips `../app` into `terraform/build/app.zip`
2. Uploads it to a new S3 bucket
3. Creates the Beanstalk application + application version
4. Creates the Beanstalk **environment** (ALB + Auto Scaling Group + EC2 — this is the slow step, ~4–6 min the first time)
5. Creates the S3 uploads bucket, DynamoDB table, IAM roles, and Cognito user pool

### Step 4 — Wait until healthy

`terraform apply` returns once the API calls succeed, but the environment takes a few more minutes to boot. Check:

```bash
aws elasticbeanstalk describe-environments \
  --environment-names $(terraform output -raw eb_environment_name) \
  --profile personal --region us-east-1 \
  --query "Environments[0].{Status:Status,Health:Health}"
```

Wait until `Status: Ready` and `Health: Green`.

### Step 5 — Open the app

```bash
terraform output app_url
```

Open that URL in a browser and click **Load Sample Menu**.

---

## Using the app

1. **Load Sample Menu** — runs all 16 sample dishes through the full pipeline (idempotent — clicking again replaces, never duplicates)
2. **Display language** dropdown — switches dish text to the Bedrock translation
3. **Diet filters** (Gluten-Free / Dairy-Free / Vegan) — OR logic; the counter shows how many dishes match
4. **Click any dish card** — review whether the LLM and rules engine agreed, override the confirmed allergens (human-in-the-loop), or delete the dish
5. **Upload a menu file** — exercises the Textract OCR path
6. **Add a dish manually** — test a single description without a file

---

## Updating after a code change

Any change under `app/` changes the zip's MD5, which Terraform uses in the application version name — so a normal apply picks it up and redeploys automatically:

```bash
cd terraform
terraform apply
```

No manual `eb deploy` needed. The rolling deploy takes ~1–2 min.

---

## Destroying everything

```bash
cd terraform
terraform destroy    # type "yes"
```

Everything is set up to tear down cleanly in one pass — no manual "empty the bucket first" step:
- Both S3 buckets: `force_destroy = true`
- Elastic Beanstalk application: removes all versions
- DynamoDB table: `deletion_protection_enabled = false`
- Nothing uses `prevent_destroy`

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `app_url` returns 502/503 | Environment still booting — re-check `describe-environments` health. If stuck, run `aws elasticbeanstalk describe-events --environment-name <name> --max-records 20 --profile personal`. |
| Dishes show `"llm_source": "offline"` | Bedrock not available (new account not verified, or wrong `bedrock_model_id`). The app keeps working via the rules engine. |
| Translations show `[Spanish - offline] ...` | Bedrock unavailable **and** Amazon Translate not activated. Both need a fully-activated AWS account. |
| Upload shows `SubscriptionRequiredException` | Textract needs a fully-activated/verified AWS account. S3 upload still succeeds; only the OCR call is blocked. |
| Bulk "Load Sample Menu" returns 504 | ALB idle timeout — already set to 300s in `beanstalk.tf`. If you lowered it, raise it back. |
| `terraform apply` IAM permission error | Your credentials can't create IAM roles. Use an admin identity or ask your AWS admin. |
| `no matching Elastic Beanstalk Solution Stack` | AWS retired the platform version. Loosen `python_version_regex` in `terraform.tfvars` to `^64bit Amazon Linux 2023.*Python 3\\.1[0-9]$`. |
| `t3.small aren't available in your VPC Subnets` | Handled in `network.tf` — subnets are filtered to AZs that offer the instance type. If you change `instance_type`, this auto-adjusts. |

---

## Cost note

Elastic Beanstalk runs an always-on EC2 instance (`t3.small`), so unlike the serverless version this costs money while running (~a few cents/hour). **Run `terraform destroy` when you're done** to stop all charges. S3, DynamoDB, Cognito, Textract, and Bedrock are pay-per-use / free-tier eligible.
