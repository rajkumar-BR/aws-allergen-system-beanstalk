# AI-Powered Allergen Compliance & Menu Translation

Flask app on Elastic Beanstalk (provisioned by Terraform). Allergen compliance
is verified by a **deterministic NZ PEAL rules engine** cross-checked against a
**Bedrock LLM** read of the dish, plus an **optional Bedrock RAG** over NZ
MPI/FSANZ regulatory docs (KB opt-in via `terraform/bedrock_kb.tf`; falls back
to bundled `docs/` when unset). Fully tear-down-able with `terraform destroy`.

**Docs:** [`ONBOARDING.md`](ONBOARDING.md) (team setup) ·
[`DEPLOY_GUIDE.md`](DEPLOY_GUIDE.md) (deploy) ·
[`docs/allergen-api.md`](docs/allergen-api.md) (service API).

## Run modes

### 1. Real AWS mode (default)

Uses IAM long-term keys from `~/.aws/credentials`; all AI features hit real AWS.

```powershell
aws configure                                  # once: AKIA key, region ap-southeast-2
.\setup_aws_env.ps1                            # sets all per-service region/resource env vars
cd app
.\.venv\Scripts\python.exe application.py      # http://localhost:8000
```

### 2. Local simulation mode (no AWS)

Offline stubs (rules engine, local `docs/`, JSON storage) — every degraded
output is labelled, e.g. `[Spanish - offline]`.

```powershell
$env:LOCAL_MODE = "true"
cd app
.\.venv\Scripts\python.exe application.py
```

## Configuration

See [`ONBOARDING.md`](ONBOARDING.md) §3 for the full step-by-step. Key facts:

- **No `.env` loader** — config comes from environment variables only (set them
  before starting the app). `.env.example` is a reference, not a loaded file.
- `setup_aws_env.ps1` sets everything for the deployed shared account.
- Resources span **two regions**, resolved per service:

| Service | Region | Env var |
|---|---|---|
| Bedrock (LLM + translation) | `ap-southeast-2` | `BEDROCK_REGION` |
| Bedrock Knowledge Base (RAG) | `ap-southeast-2` | `KB_REGION` |
| DynamoDB | `us-east-1` | `DYNAMODB_REGION` |
| S3 (menu uploads) | `us-east-1` | `S3_REGION` |
| Textract | `us-east-1` | `TEXTRACT_REGION` |

> ⚠️ Module defaults for `DYNAMODB_TABLE` / `S3_BUCKET` are **not** the deployed
> names (and `S3_BUCKET` defaults empty → uploads disabled). Without
> `setup_aws_env.ps1` (or manual exports), DynamoDB fails with
> `ResourceNotFoundException` and S3 uploads are unavailable.

## Allergen source of truth

NZ MPI [mandatory declarable allergens](https://www.mpi.govt.nz/food-business/labelling-composition-food-drinks/allergen-declarations-warnings-and-advisory-statements-on-food-labels):
peanuts, tree nuts (each declared individually), crustacean, **molluscs**, fish,
milk, egg, wheat, soy, sesame, lupin — plus gluten (from wheat/rye/barley/oats/
spelt/triticale) and added sulphites (>10 mg/kg). Implemented in
`app/services/allergen_rules.py` (`PEAL_CATEGORIES`).

## Repo layout

```
app/                    Flask app (zipped + deployed to Beanstalk)
  application.py        Routes + pipeline
  services/             allergen_rules / allergen_service / bedrock_service /
                        dynamo_service / s3_service / textract_service
  static/               UI (index.html / style.css / app.js)
  sample_data/          16 sample dishes
  requirements.txt      Flask, boto3==1.43.88, gunicorn
terraform/              All infra (beanstalk / s3 / dynamodb / iam / bedrock_kb / cognito)
setup_aws_env.ps1       One-stop env config (regions, resources, KB id, model)
```

## AWS credentials

`aws configure` writes keys to `~/.aws/credentials` (`[default]`) and region to
`~/.aws/config`. **Never commit these files.** Verify with
`aws sts get-caller-identity` (expect an IAM user ARN).

For the full IAM-user setup steps (creating the user/policy, `aws configure`
walkthrough, file paths), see [`ONBOARDING.md`](ONBOARDING.md) §2.

## Deploy / destroy

```powershell
cd terraform
terraform init && terraform apply     # see DEPLOY_GUIDE.md; ~4-6 min to ready
terraform destroy                     # clean teardown (force_destroy set on S3, etc.)
```

## API

`POST /api/allergens/extract` · `POST /api/compliance/verify` · menu CRUD /
seed / upload routes. Contract details in
[`docs/allergen-api.md`](docs/allergen-api.md).