# Knowledge Base 完整配置指南

## 一、需要配置什么？

Knowledge Base 需要以下组件：

| 组件 | 用途 | 是否需要手动配置 |
|------|------|-----------------|
| **S3 Bucket** | 存放法规文档 | ❌ Terraform 自动创建 |
| **Knowledge Base** | RAG 检索服务 | ❌ Terraform 自动创建 |
| **OpenSearch Serverless** | 向量存储 | ❌ Terraform 自动创建 |
| **Service Role** | KB 访问权限 | ❌ Terraform 自动创建 |
| **Knowledge Base ID** | 应用连接 ID | ✅ 需要从 Terraform 输出获取 |
| **Ingestion Job** | 文档索引 | ✅ 需要手动触发 |

---

## 二、步骤 1：修改 Terraform 配置

编辑 `terraform/terraform.tfvars`：

```hcl
# 启用 Knowledge Base 创建
create_knowledge_base = true

# （可选）指定 embedding 模型（默认已配置）
bedrock_embedding_model_arn = "arn:aws:bedrock:ap-southeast-2::foundation-model/amazon.titan-embed-text-v2:0"
```

---

## 三、步骤 2：运行 Terraform 创建资源

```bash
cd terraform

# 初始化（首次运行）
terraform init

# 查看将要创建的资源
terraform plan -var="create_knowledge_base=true"

# 应用配置
terraform apply -var="create_knowledge_base=true"
```

### 预期输出

```
aws_s3_bucket.kb_docs[0]: Creating...
aws_iam_role.kb_service_role[0]: Creating...
aws_opensearchserverless_collection.peal[0]: Creating...
aws_bedrockagent_knowledge_base.peal[0]: Creating...
aws_bedrockagent_data_source.peal[0]: Creating...

Apply complete! Resources: 8 added, 0 changed, 0 destroyed.
```

---

## 四、步骤 3：获取 Knowledge Base ID

### 方法 1：从 Terraform 输出获取

添加到 `terraform/outputs.tf`：

```hcl
output "knowledge_base_id" {
  value       = var.create_knowledge_base ? aws_bedrockagent_knowledge_base.peal[0].id : ""
  description = "Bedrock Knowledge Base ID for RAG retrieval"
}

output "knowledge_base_arn" {
  value       = var.create_knowledge_base ? aws_bedrockagent_knowledge_base.peal[0].arn : ""
  description = "Bedrock Knowledge Base ARN"
}

output "kb_docs_bucket" {
  value       = var.create_knowledge_base ? aws_s3_bucket.kb_docs[0].bucket : ""
  description = "S3 bucket containing PEAL reference documents"
}
```

然后运行：

```bash
terraform apply -var="create_knowledge_base=true"
terraform output knowledge_base_id
```

### 方法 2：从 AWS Console 获取

1. 登录 AWS Console
2. 导航到 **Amazon Bedrock** → **Knowledge Bases**
3. 找到名为 `allergen-demo-peal-kb` 的 Knowledge Base
4. 复制 **Knowledge Base ID**（格式：`ABCDEFGHIJ`）

### 方法 3：使用 AWS CLI

```bash
aws bedrock-agent list-knowledge-bases \
  --region ap-southeast-2 \
  --query "knowledgeBaseSummaries[?contains(name, 'peal')].{ID:id, Name:name}"
```

---

## 五、步骤 4：配置应用到 Knowledge Base

### 方法 1：设置环境变量

```bash
# 设置 Knowledge Base ID
export KNOWLEDGE_BASE_ID=ABCDEFGHIJ

# 设置 AWS 区域
export AWS_REGION=ap-southeast-2

# 禁用本地模式
export LOCAL_MODE=false
```

### 方法 2：修改 Beanstalk 环境变量

编辑 `terraform/beanstalk.tf`，找到环境变量配置部分：

```hcl
# 在现有的环境变量后面添加
setting {
  namespace = "aws:elasticbeanstalk:application:environment"
  name      = "KNOWLEDGE_BASE_ID"
  value     = aws_bedrockagent_knowledge_base.peal[0].id
}
```

然后重新部署：

```bash
terraform apply
```

### 方法 3：使用 `.env` 文件（本地开发）

创建 `app/.env` 文件：

```env
KNOWLEDGE_BASE_ID=ABCDEFGHIJ
AWS_REGION=ap-southeast-2
LOCAL_MODE=false
```

---

## 六、步骤 5：触发文档 Ingestion

Knowledge Base 创建后，需要触发文档索引：

### 方法 1：AWS Console

1. 导航到 **Bedrock** → **Knowledge Bases**
2. 选择你的 Knowledge Base
3. 点击 **Data sources** 标签
4. 选择数据源
5. 点击 **Sync** 按钮

### 方法 2：AWS CLI

```bash
# 获取 Data Source ID
aws bedrock-agent list-data-sources \
  --knowledge-base-id YOUR_KB_ID \
  --region ap-southeast-2

# 触发 ingestion job
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id YOUR_KB_ID \
  --data-source-id YOUR_DS_ID \
  --region ap-southeast-2
```

### 方法 3：在 Terraform 中自动触发（可选）

添加到 `terraform/bedrock_kb.tf`：

```hcl
# 注意：这可能增加 Terraform apply 时间
resource "null_resource" "trigger_ingestion" {
  count = var.create_knowledge_base ? 1 : 0
  
  provisioner "local-exec" {
    command = <<-EOT
      aws bedrock-agent start-ingestion-job \
        --knowledge-base-id ${aws_bedrockagent_knowledge_base.peal[0].id} \
        --data-source-id ${aws_bedrockagent_data_source.peal[0].id} \
        --region ${var.aws_region}
    EOT
  }
  
  depends_on = [
    aws_bedrockagent_data_source.peal
  ]
}
```

---

## 七、步骤 6：验证配置

### 检查 S3 文档

```bash
# 列出已上传的文档
aws s3 ls s3://allergen-demo-kb-docs-ACCOUNT_ID/nz-peal/

# 预期输出：
# PRE nz-peal/
# 2024-XX-XX XX:XX:XX XXXX nz_peal_allergens.md
```

### 检查 Knowledge Base 状态

```bash
aws bedrock-agent get-knowledge-base \
  --knowledge-base-id YOUR_KB_ID \
  --region ap-southeast-2
```

### 测试检索

```bash
python scripts/quick_test_kb.py
```

---

## 八、完整配置清单

### 必需配置

| 配置项 | 来源 | 示例值 |
|--------|------|--------|
| `KNOWLEDGE_BASE_ID` | Terraform 输出 | `ABCDEFGHIJ` |
| `AWS_REGION` | 固定 | `ap-southeast-2` |
| `LOCAL_MODE` | 固定 | `false` |

### AWS 资源（Terraform 自动创建）

| 资源 | 名称模式 | 说明 |
|------|----------|------|
| S3 Bucket | `allergen-demo-kb-docs-*` | 存放法规文档 |
| Knowledge Base | `allergen-demo-peal-kb` | RAG 服务 |
| OpenSearch Collection | `allergen-demo-peal` | 向量存储 |
| IAM Role | `allergen-demo-bedrock-kb-role` | 服务角色 |

### IAM 权限（自动配置）

你的执行身份需要以下权限：

```json
{
  "Effect": "Allow",
  "Action": [
    "bedrock-agent:CreateKnowledgeBase",
    "bedrock-agent:CreateDataSource",
    "bedrock-agent:StartIngestionJob",
    "aoss:CreateCollection",
    "aoss:CreateSecurityPolicy"
  ],
  "Resource": "*"
}
```

---

## 九、常见问题

### 1. Terraform apply 失败：权限不足

**错误信息**：
```
Error: AccessDeniedException: User is not authorized to perform: bedrock-agent:CreateKnowledgeBase
```

**解决方法**：
确保你的 AWS 身份有以下权限：
- `bedrock-agent:*`
- `aoss:*`
- `iam:CreateRole`
- `s3:CreateBucket`

### 2. Knowledge Base ID 为空

**可能原因**：
- `create_knowledge_base = false`（默认值）
- Terraform apply 未完成

**解决方法**：
```bash
# 确认配置
grep "create_knowledge_base" terraform/terraform.tfvars

# 重新 apply
terraform apply -var="create_knowledge_base=true"
```

### 3. Ingestion 后仍无结果

**检查步骤**：
```bash
# 1. 检查文档是否上传
aws s3 ls s3://YOUR_KB_BUCKET/nz-peal/

# 2. 检查 ingestion job 状态
aws bedrock-agent list-ingestion-jobs \
  --knowledge-base-id YOUR_KB_ID \
  --data-source-id YOUR_DS_ID

# 3. 检查 OpenSearch 索引
aws opensearchserverless list-collections
```

---

## 十、快速检查清单

```bash
# 1. 检查 Terraform 变量
terraform console
> var.create_knowledge_base
true

# 2. 检查 Knowledge Base 是否创建
aws bedrock-agent list-knowledge-bases --region ap-southeast-2

# 3. 检查 S3 文档
aws s3 ls s3://$(terraform output -raw kb_docs_bucket)/nz-peal/

# 4. 测试检索
export KNOWLEDGE_BASE_ID=$(terraform output -raw knowledge_base_id)
python scripts/quick_test_kb.py
```

---

## 十一、下一步

配置完成后，你可以：

1. **测试 RAG 检索**
   ```bash
   python scripts/test_knowledge_base.py --aws
   ```

2. **测试完整流程**
   ```bash
   python scripts/test_claude_extraction.py --live
   ```

3. **集成到应用**
   - 代码会自动使用 Knowledge Base
   - 无需修改代码逻辑
