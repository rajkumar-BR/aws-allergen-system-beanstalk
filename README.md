# AI-Powered Allergen Compliance & Menu Translation - Beanstalk Edition

This is a from-scratch rebuild of the project in `AI_Allergen_Compliance_Presentation.pdf`, hosted on Elastic Beanstalk (per your request). Compliance verification runs a deterministic NZ PEAL rules engine cross-checked against a Bedrock LLM read of the dish, plus an **optional** Bedrock RAG knowledge base of the NZ MPI / FSANZ regulatory docs that adds grounded citations when deployed (opt-in via `terraform/bedrock_kb.tf`). Without the KB the app degrades to a bundled local retrieval (`docs/`), so everything still works with zero AWS dependencies.

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
| Bedrock LLM anchored on NZ MPI PEAL knowledge base | Allergens are extracted by a Bedrock LLM call and cross-checked by a deterministic keyword rules engine (`app/services/allergen_rules.py`). Compliance is then verified with an optional Bedrock RAG layer: `app/services/allergen_service.py::retrieve_context` retrieves NZ PEAL regulatory context (from the Bedrock KB when `KNOWLEDGE_BASE_ID` is set, otherwise a bundled local retrieval over `docs/`) and `app/services/allergen_service.py::verify` produces the final "Contains X" set plus per-allergen regulatory citations. The union of all signals is shown to the diner; disagreements are flagged for human review |
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
    allergen_rules.py     FSANZ 1.2.3 rules engine (deterministic scan)
    allergen_service.py   Orchestration: extract / verify / RAG retrieve /
                          pipeline merge (+ local fallbacks)
    bedrock_service.py    Bedrock allergen extraction + translation
    textract_service.py   OCR
    dynamo_service.py     DynamoDB CRUD (+ local JSON fallback)
    s3_service.py         Raw file storage (+ local fallback)
  static/                 UI (index.html / style.css / app.js)
  sample_data/
    sample_menu.json      16 sample dishes used by "Load Sample Menu"
  requirements.txt
  Procfile                gunicorn entry point Beanstalk uses

terraform/              All infrastructure, Beanstalk included
  beanstalk.tf            Zips app/, uploads it, creates the EB app/env
  s3.tf                    2 buckets (uploads + EB app version bundles),
                           both force_destroy = true
  dynamodb.tf              Menu items table, deletion_protection disabled
  iam.tf                   EC2 instance role (Bedrock/Textract/S3/Dynamo/
                           Translate/Retrieve) + EB service role
  bedrock_kb.tf            OPT-IN Bedrock Knowledge Base for the compliance
                           RAG layer (disabled unless create_knowledge_base=true)
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

#### Where the IAM credentials live on Windows (long-term key mode)

This project is set up to use **IAM long-term keys** (AKIA-prefixed, never
expire) as the primary auth mode, so no SSO re-login is needed. The keys are
stored in the standard AWS CLI files under your user profile (NOT in the
repository):

| Item | File | Example |
|---|---|---|
| Access Key ID + Secret | `C:\Users\<you>\.aws\credentials` | `[default] aws_access_key_id=AKIA...` |
| Region / output format | `C:\Users\<you>\.aws\config` | `[default] region = ap-southeast-2` |

- They live under `[default]`, so **no `AWS_PROFILE` or env vars are required** -
  the SDK picks them up automatically.
- Current account for this project: **`YOUR_AWS_ACCOUNT_ID`** (IAM user `allergen-system-dev`),
  region **`ap-southeast-2`**.
- Verify which identity you're using: `aws sts get-caller-identity`.
  - `arn:aws:iam::...:user/...` → IAM long-term key (good).
  - `arn:aws:sts::...:assumed-role/AWSReservedSSO_...` → you logged in with SSO.

> ⚠️ **Security**: `~/.aws/credentials` stores keys in plaintext. Never commit
> that file or paste real keys into code/scripts (the repo excludes `.env`).

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

## Configuration — how and where

### How configuration works

- **The app does NOT read a `.env` file.** There is no `python-dotenv`; config
  comes only from **environment variables** (plus hard-coded module defaults as
  a last resort). Do not rely on copying `.env.example` to `.env` — it won't be
  picked up. `.env.example` exists only as a human-readable reference of the
  variables.
- Each service module reads its variables **once at import time**, so the
  environment variables must be set **before** the app starts (same shell
  session), not after.
- **The one-stop config script is `setup_aws_env.ps1`** (repo root). It sets
  every variable below correctly (regions, resource names, model, KB id) for
  the deployed shared account. Run it in every terminal before starting the
  app:
  ```powershell
  .\setup_aws_env.ps1
  ```
  Alternatively export the same variables manually (see the table below).
  Everything the script sets is listed in it, so it is the authoritative
  reference for the current deployment values.

### Where configuration lives

| What | Where | Notes |
|---|---|---|
| **AWS credentials** (AKIA key + secret) | `~/.aws/credentials` (`[default]`) | configured once via `aws configure`; never committed |
| **AWS CLI region/output** | `~/.aws/config` | `region`, `output` |
| **App runtime config** (regions, resources, model, KB) | environment variables set by `setup_aws_env.ps1` | per PowerShell session |
| **Delegate defaults** | `app/services/*.py` module-level `os.environ.get(...)` | fallback only; see table |
| **Deployment config** | `terraform/terraform.tfvars` (git-ignored) | only used by `terraform deploy` |

### Environment variables

| Variable | Default if unset | Set by `setup_aws_env.ps1` | Purpose |
|---|---|---|---|
| `AWS_REGION` | `ap-southeast-2` (Bedrock) / `us-east-1` (others) | `ap-southeast-2` | general fallback region |
| `BEDROCK_REGION` | `AWS_REGION` | `ap-southeast-2` | Bedrock runtime region |
| `KB_REGION` | `AWS_REGION` | `ap-southeast-2` | Bedrock Knowledge Base region |
| `DYNAMODB_REGION` | `AWS_REGION`→`us-east-1` | `us-east-1` | DynamoDB table region |
| `S3_REGION` | `AWS_REGION`→`us-east-1` | `us-east-1` | S3 uploads bucket region |
| `TEXTRACT_REGION` | `AWS_REGION`→`us-east-1` | `us-east-1` | Textract region |
| `BEDROCK_MODEL_ID` | `au.anthropic.claude-opus-4-6-v1` | same | inference-profile model id |
| `KNOWLEDGE_BASE_ID` | `""` (RAG degrades to local) | `CBFZTLLUHU` | Bedrock KB for RAG |
| `DYNAMODB_TABLE` | `allergen-menu-items` **stale** | `allergen-demo-dev-menu-items` | DynamoDB table name |
| `S3_BUCKET` | `""` (S3 disabled) | `allergen-demo-dev-menu-uploads-669232219904` | S3 uploads bucket name |
| `LOCAL_MODE` | `false` | `false` | `true` = offline stubs |
| `PORT` | `8000` | — | Flask port |

> ⚠️ **Why the script is required for real AWS mode:** the module defaults for
> `DYNAMODB_TABLE` and `S3_BUCKET` are **not** the deployed resource names, and
> `S3_BUCKET` defaults to empty (S3 uploads disabled). Without
> `setup_aws_env.ps1` (or the same variables exported manually), DynamoDB
> queries fail with `ResourceNotFoundException` and S3 uploads are unavailable —
> even though Bedrock and RAG would still work.

## Run modes

> 🧑‍🤝‍🧑 **New team member?** There is a full step-by-step onboarding guide
> (shared enterprise account, from clone to running against the cloud) in
> **[`ONBOARDING.md`](ONBOARDING.md)** — follow that instead of this section.

This project supports two run modes:

### **1. Real AWS mode (default, recommended)**

Uses the IAM long-term credentials in `~/.aws/credentials` (AKIA-prefixed), so
**no repeated login is needed**, and all AI features hit real AWS services.

**Start (Windows PowerShell):**

```powershell
# Configure long-term credentials once (IAM user access key)
aws configure
#   AWS Access Key ID: AKIA...
#   Secret Access Key: ********
#   Default region name: ap-southeast-2
#   Default output format: json

# Set per-service region env vars (recommended: use setup_aws_env.ps1)
.\setup_aws_env.ps1     # sets all region/resource-name env vars

# Start the app
cd app
.\.venv\Scripts\python.exe application.py
# Open http://localhost:8000
```

**Per-service regions (important):** this project's resources span two AWS
regions, so `setup_aws_env.ps1` / the service code resolve a region per
service:

| Service | Region | Notes |
|---|---|---|
| Bedrock (extraction + translation) | `ap-southeast-2` | inference profile region |
| Knowledge Base (RAG) | `ap-southeast-2` | KB `YOUR_KNOWLEDGE_BASE_ID` |
| DynamoDB | `us-east-1` | table `allergen-demo-dev-menu-items` |
| S3 (menu uploads bucket) | `us-east-1` | bucket `allergen-demo-dev-menu-uploads-...` |
| Textract | `us-east-1` | OCR |

Each service module supports its own region override variable
(`BEDROCK_REGION` / `KB_REGION` / `DYNAMODB_REGION` / `S3_REGION` /
`TEXTRACT_REGION`), falling back to `AWS_REGION` when unset.

**Verify your identity:**

```
aws sts get-caller-identity
# arn:aws:iam::...:user/...  → IAM long-term credentials (correct)
```

### **2. Local simulation mode (no AWS)**

No AWS account needed — uses the local rules engine + local docs + JSON file
storage, handy for offline development and UI debugging.

```powershell
# Windows PowerShell
$env:LOCAL_MODE = "true"
cd app
.\.venv\Scripts\python.exe application.py
```

In local mode, Bedrock → keyword rules engine, RAG → local `docs/*.md`, S3 →
temp directory, DynamoDB → JSON file; every degraded output is clearly labelled
(e.g. `[Spanish - offline]`).

**Local-mode service mapping:**

| AWS service | Local replacement |
|---|---|
| Bedrock | rules engine + keyword matching |
| Knowledge Base | local `docs/` document retrieval |
| Textract | text file parsing |
| S3 | temp directory |
| DynamoDB | JSON file (`%TEMP%\allergen_local_db.json`) |

**End-to-end local-mode check (no AWS):**

```powershell
cd app
$env:LOCAL_MODE='true'
.\.venv\Scripts\python.exe -c "
from services import allergen_service as svc
e = svc.extract('Seafood Chowder', 'creamy soup with fish, prawns and milk')
print('Extracted:', [a.name for a in e.allergens])
c = svc.verify('Seafood Chowder', ['Fish','Crustacea','Milk'])
print('Compliance:', c.status)
r = svc.retrieve_context('fish requirements')
print('RAG chunks:', len(r['chunks']))
"
```

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

---

## Allergen & Compliance service (deliverable)

This section documents the **Allergen Extraction + Compliance Verification**
workstream — the deliverable focused on by this repo's owning team.
It is kept independent of OCR, Translation and UI so the rest of the team can
consume a clean API.

### Which parts are LLM / RAG / Deterministic

| Concern | Engine | Where |
|---|---|---|
| Allergen extraction (primary signal) | **LLM via Bedrock Tool Use** | `services/bedrock_service.py` — `extract_allergens_tool_use` |
| Allergen extraction (cross-check / fallback) | **Deterministic** keyword rules | `services/allergen_rules.py` — `scan_text_for_allergens` |
| Regulatory retrieval | **RAG** — Bedrock Knowledge Base (AWS) or bundled `docs/` (local) | `services/allergen_service.py` — `retrieve_context` / `_retrieve_kb_aws` / `_search_kb_local` |
| Compliance verdict & declarations | **Deterministic** rules engine | `services/allergen_service.py` — `verify` / `evaluate_compliance` |
| Public orchestration / reconciliation | Deterministic merge (Bedrock + rules + RAG) | `services/allergen_service.py` — `extract` / `verify_pipeline` / `_run_pipeline` |

The final regulatory decision is **never made by the LLM alone** — the
deterministic rules engine reconciles and issues declaration / warning /
advisory statements (task Principle 1).

### Contracts (defined in `services/allergen_service.py`)

- `ExtractRequest` → `{dish_name, description}`
- `Allergen` → `{name, evidence, status, confidence}`
  - `status` ∈ `CONFIRMED | POSSIBLE | UNKNOWN`. `POSSIBLE`/`UNKNOWN` are never
    silently reported as compliant.
- `ExtractionResult` → `{dish_name, allergens[], engine, llm_reasoning?}`
- `ComplianceResult` → `{dish_name, allergens[], compliance, sources}`
  - `compliance.status` ∈ `COMPLIANT | ACTION_REQUIRED | UNVERIFIED`
  - `compliance` distinguishes `allergen_declarations`,
    `warning_statements`, `advisory_statements` (never a single `warning`).

### API

```
POST /api/allergens/extract
  { "dish_name": "...", "description": "..." }
  -> { "dish_name": "...", "allergens": [
        {"name": "Cashew", "evidence": "cashew nuts", "status": "CONFIRMED", "confidence": 0.99}, ...] }

POST /api/compliance/verify
  { "dish_name": "...", "description": "...", "allergens": [ ...optional in-advance extraction... ] }
  -> { "dish_name": "...", "compliance": {
        "status": "COMPLIANT",
        "allergen_declarations": ["Contains Cashews", "Contains Milk"],
        "warning_statements": [],
        "advisory_statements": [] }, "sources": [ ... ] }
```

Both accept either `dish_name` or the legacy `name` field. The route handlers
live in `app/application.py` and delegate to `services/allergen_service.py`.

### Function Calling / Tool Use

`services/bedrock_service.py::extract_allergens_tool_use` drives extraction
through a real Claude tool call. The JSON Schema in `_EXTRACT_ALLERGEN_TOOL`
forces a structured `toolUse.input` (per-allergen name/evidence/status/
confidence) instead of free-form prose. If Bedrock is unavailable (broken
credentials, no model access, offline) it degrades to the deterministic engine,
so the pipeline never hard-fails.

### Running & testing

No AWS account needed to exercise the deterministic path (`LOCAL_MODE=true`):

```powershell
# Windows PowerShell — start in local mode, then hit the API
$env:LOCAL_MODE = "true"
cd app
.\.venv\Scripts\python.exe application.py
# then: Invoke-WebRequest http://localhost:8000/api/allergens/extract -Method POST -Body '{"dish_name":"...","description":"..."}' -ContentType 'application/json'
```

For the real AWS path (Bedrock + KB + DynamoDB + S3), set `LOCAL_MODE=false`
(or unset it — false is the module default), set the per-service region
variables (see `setup_aws_env.ps1`), and use valid IAM credentials in
`~/.aws/credentials`. Set `BEDROCK_MODEL_ID` if you need a different Claude
model (must be an inference-profile id such as `au.anthropic.claude-opus-4-6-v1`,
not a bare foundation-model id).

### Regulatory sources

The canonical allergen taxonomy follows the NZ MPI page
[Allergen declarations, warnings and advisory statements on food labels](
https://www.mpi.govt.nz/food-business/labelling-composition-food-drinks/allergen-declarations-warnings-and-advisory-statements-on-food-labels)
and FSANZ Standard 1.2.3. Bundled reference copies used for local retrieval are
in `docs/` (e.g. `nz_peal_allergens.md` and the MPI/FSANZ PDFs; the same docs
can be uploaded to the optional Bedrock Knowledge Base referenced by
`KNOWLEDGE_BASE_ID`).

### Known limitations

- The deterministic keyword engine is a starting point and must be reviewed by a
  food-safety qualified person before commercial use; it is not exhaustive.
- Tree nuts are declared individually (per NZ MPI); the engine intentionally does
  not collapse them into a generic "Nuts".
- Uncertain/sulphite cases are surfaced as `POSSIBLE` / `ACTION_REQUIRED`,
  never auto-confirmed, pending human review.

