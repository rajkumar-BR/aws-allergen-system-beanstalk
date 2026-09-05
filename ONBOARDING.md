# Team Onboarding — Run the App Against Shared AWS (Enterprise Account)

This guide is for **team members** who just cloned the repo and want to run the
app against the **shared enterprise AWS account** (real cloud services: Bedrock,
Knowledge Base, DynamoDB, S3, Textract, Translate). If you only want the offline
local mode (no AWS), skip to [Section 4](#4-offline-local-mode-no-aws).

---

## What you need before you start

| Item | Where from | Notes |
|---|---|---|
| AWS credentials for the **shared account** | Your AWS admin (enterprise account) | Long-term IAM keys (`AKIA...`) or SSO access |
| Python 3.11+ | python.org / enterprise toolchain | 3.13 verified |
| The repo | `git clone <repo-url>` | |

> The repo itself contains **no credentials** and **no hard-coded secrets**.
> Credentials live only in `~/.aws/` on each machine.

---

## 1. Install Python dependencies (one-time)

```powershell
cd app
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

This installs `Flask`, `boto3==1.43.88` (>=1.36 required for Bedrock Knowledge
Base managed retrieval), `gunicorn`, `Werkzeug`.

---

## 2. Configure AWS credentials (one-time, per machine)

You need credentials for the **enterprise account** that owns the deployed
resources (Bedrock KB `YOUR_KNOWLEDGE_BASE_ID`, DynamoDB table, S3 bucket).

### Option A — IAM long-term keys (simplest, recommended)

Get an access key from your admin, then:

```powershell
aws configure
# AWS Access Key ID: AKIA...
# AWS Secret Access Key: ********
# Default region name: ap-southeast-2
# Default output format: json
```

Verify:

```powershell
aws sts get-caller-identity
# Should show the enterprise account ID (e.g. 123456789012) and your IAM user.
```

### Option B — AWS SSO (if your team uses Identity Center)

```powershell
aws configure sso          # follow prompts, use your enterprise SSO start URL
aws sso login --profile <your-profile>
$env:AWS_PROFILE = "<your-profile>"
```

Either way, the app uses whatever `boto3` resolves from the default chain.

---

## 3. Set environment variables and run (real AWS mode)

The app is **split across two regions**, so the setup script sets per-service
region overrides (a single `AWS_REGION` cannot serve both):

| Service | Region | Variable |
|---|---|---|
| Bedrock inference profile | `ap-southeast-2` | `BEDROCK_REGION` |
| Bedrock Knowledge Base (RAG) | `ap-southeast-2` | `KB_REGION` |
| DynamoDB table | `us-east-1` | `DYNAMODB_REGION` |
| S3 menu-uploads bucket | `us-east-1` | `S3_REGION` |
| Textract OCR | `us-east-1` | `TEXTRACT_REGION` |

Run the setup script (sets **all** variables, including resource names and the
KB id), then start the app:

```powershell
# from the repo root
.\setup_aws_env.ps1

cd app
.\.venv\Scripts\python.exe application.py
```

Then open http://localhost:8000 in your browser.

> **Note:** the env vars set by `setup_aws_env.ps1` only last for the current
> PowerShell session. Re-run it in every new terminal before starting the app,
> or run the two commands in the same session.

### What "real AWS mode" means

- `/health` returns `"local_mode": "false"`
- Allergen extraction → **Bedrock** (`engine: bedrock-tool-use`)
- Compliance citations → **Bedrock Knowledge Base** (KB `YOUR_KNOWLEDGE_BASE_ID`, `engine=aws`)
- Storage → **DynamoDB** (`allergen-demo-dev-menu-items`) + **S3**
- Translation → **Bedrock** with Amazon Translate fallback
- Menu file upload → **Textract OCR**

### What you need permission for

The enterprise account's IAM policy for this app grants the minimal set the
app calls:

```
bedrock:Converse / InvokeModel / Retrieve (bedrock-agent-runtime)
dynamodb:PutItem / GetItem / Query / Scan / UpdateItem / DeleteItem
s3:PutObject / GetObject / ListBucket
textract:DetectDocumentText
translate:TranslateText
```

If you hit an AccessDenied error, ask your admin to attach the app's IAM
policy (same permissions list) to your user/role.

---

## 4. Offline local mode (no AWS)

If you don't have credentials yet and just want to try the UI:

```powershell
cd app
$env:LOCAL_MODE = "true"
.\.venv\Scripts\python.exe application.py
```

Everything AWS-shaped is replaced with clearly-labelled stubs
(offline rules engine, local `docs/` retrieval, JSON file storage), so the UI
and rules engine still work.

---

## 5. Verify it is really talking to AWS

| Symptom | Meaning |
|---|---|
| `/health` → `"local_mode": "false"` | Real AWS mode on |
| `POST /api/allergens/extract` → `"engine": "bedrock-tool-use"` | Bedrock extraction hit |
| Dish card shows a regulatory citation (MPI/FSANZ PDF source) | KB RAG hit (`engine=aws`) |
| `"engine": "rules"` / `llm_source: offline` | Bedrock call failed → fell back offline (check credentials / model access / quota) |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `No credentials found` / `Unable to locate credentials` | `aws configure` again; confirm `~/.aws/credentials` has `[default]` |
| `AccessDenied` on Bedrock/DynamoDB/S3 | Ask admin to attach the app IAM policy to your user/role |
| `ResourceNotFoundException` on DynamoDB | You're querying the wrong table or region — confirm `DYNAMODB_REGION=us-east-1` and table `allergen-demo-dev-menu-items` |
| RAG falls back to local (`Incompatible configuration: vectorSearchConfiguration ...`) | `boto3` too old — `pip install -r requirements.txt` (pins 1.43.88) |
| Translations show `[Spanish - offline]` | Bedrock/Translate unavailable — check credentials and model access |
| Port 8000 in use | `$env:PORT=8080` then start again |
| PowerShell blocks the script | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` then re-run `.\setup_aws_env.ps1` |

---

## Deploying to Elastic Beanstalk (optional, admins only)

See `DEPLOY_GUIDE.md`. Typical steps:

```powershell
cd terraform
terraform init
terraform plan
terraform apply
```

After apply, the Beanstalk environment injects `BEDROCK_MODEL_ID` and
`KNOWLEDGE_BASE_ID` from Terraform variables; the app on EC2 uses the same
per-service region defaults baked into `app/services/*.py`.