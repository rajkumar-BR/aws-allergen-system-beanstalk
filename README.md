# AI-Powered Allergen Compliance & Menu Translation - Beanstalk Edition

This is a from-scratch rebuild of the project in `AI_Allergen_Compliance_Presentation.pdf`,
swapping **AWS Amplify** for **Elastic Beanstalk** (per your request) and
removing the **Bedrock knowledge-base / RAG** component - compliance
verification is done with a deterministic rules engine instead.

Everything is provisioned with **Terraform** and is fully tear-down-able
with `terraform destroy` (see "Destroying everything" below).

## What actually runs where

| PDF architecture item | This build |
|---|---|
| AWS Amplify hosting | **Elastic Beanstalk** (Python 3.12 on Amazon Linux 2023), provisioned by Terraform |
| API Gateway + Cognito auth | Not required - Beanstalk's own load balancer serves the app directly. A Cognito User Pool is still provisioned (`terraform/cognito.tf`) to cover that checklist item for later use, but the demo UI does not enforce login yet |
| Lambda two-step chain (Analyze -> Translate) | Runs as two plain function calls inside one Flask request (`app/application.py: _run_pipeline`) - no Lambda needed once the app has its own always-on compute (Beanstalk) |
| Bedrock RAG anchored on NZ MPI PEAL knowledge base | **Removed per your instruction.** Allergens are extracted by a Bedrock LLM call *and* cross-checked by a deterministic keyword rules engine (`app/services/allergen_rules.py`) built directly from the FSANZ Standard 1.2.3 mandatory declarable allergen list. The union of both is what's shown as "Contains X"; disagreements are flagged for human review |
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

## Quick start (real AWS deployment)

See `DEPLOY_GUIDE.md` for the full walkthrough. Short version:

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # edit region etc. if needed
terraform init
terraform apply
```

Wait for the environment to go "Green"/"Ready" (takes ~4-6 minutes the
first time), then open the `app_url` output in a browser and click
**"Load Sample Menu"**.

## Testing without any AWS account first

```bash
./run_local.sh
```

Then open http://localhost:8000. This runs the identical Flask app/UI
with Bedrock/Textract/S3/DynamoDB replaced by clearly-labelled offline
stubs (still runs the real FSANZ rules engine), so you can confirm the
UI/flow works before spending anything on AWS.

## Destroying everything

```bash
cd terraform
terraform destroy
```

Every resource that can normally block a clean teardown has been set
up to allow it:
- Both S3 buckets: `force_destroy = true` (deletes non-empty buckets)
- Elastic Beanstalk application: `force_delete = true` (removes all
  application versions first)
- DynamoDB table: `deletion_protection_enabled = false`

Nothing here uses `prevent_destroy`, so a single `terraform destroy`
tears down the whole stack in one pass.
