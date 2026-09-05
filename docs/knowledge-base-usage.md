# Knowledge Base 使用指南

## 一、在代码中使用 Knowledge Base

### 1. 基本用法

```python
from services.rag_service import retrieve_context, is_available

# 检查 Knowledge Base 是否可用
if is_available():
    print("✅ Knowledge Base 可用")

# 检索法规上下文
query = "What are the allergen declaration requirements for peanuts?"
result = retrieve_context(query, top_k=5)

print(f"引擎: {result['engine']}")  # 'aws', 'local', 或 'none'
print(f"找到 {len(result['chunks'])} 个相关片段")

# 访问检索结果
for chunk in result['chunks']:
    print(f"来源: {chunk['source']}")
    print(f"内容: {chunk['text']}")
    print(f"分数: {chunk['score']}")
```

### 2. 在 Compliance Verification 中使用

Knowledge Base 已集成到 `compliance_service.verify_compliance()`:

```python
from services.allergen_service import verify
from services.rag_service import retrieve_context

# 方式 1: 直接调用 verify（会自动调用 RAG）
result = verify("Chicken Satay", allergens=["peanuts", "soy"])
print(result.to_json())

# 方式 2: 手动调用 RAG
dish_text = "Chicken Satay with peanut sauce"
retrieval = retrieve_context(dish_text)

# retrieval 结构:
# {
#     "engine": "aws" | "local" | "none",
#     "chunks": [
#         {
#             "text": "...regulation text...",
#             "source": "s3://bucket/...",
#             "section": "Peanuts",
#             "score": 0.85
#         }
#     ]
# }
```

### 3. 在 Pipeline 中使用

完整的端到端流程：

```python
from services.allergen_service import extract
from services.rag_service import retrieve_context
from services.compliance_engine import verify_compliance

# 步骤 1: 过敏原抽取
dish_name = "Seafood Chowder"
description = "Creamy soup with fish, prawns and milk"
extraction = extract(dish_name, description)

# 步骤 2: RAG 检索法规证据
dish_text = f"{dish_name} {description}"
retrieval = retrieve_context(dish_text, top_k=5)

# 步骤 3: 合规判定（结合 RAG 结果）
# compliance_service 会使用 retrieval 结果
from services.compliance_service import verify_compliance
compliance = verify_compliance(
    dish_name,
    description,
    extraction.confirmed_names,  # LLM 抽取的过敏原
    [],  # 规则引擎结果（可选）
    retrieval  # RAG 检索结果
)
```

## 二、环境配置

### 必需的环境变量

```bash
# Knowledge Base ID（从 Terraform 或 Console 获取）
export KNOWLEDGE_BASE_ID=ABCDEFGHIJ

# AWS 区域
export AWS_REGION=ap-southeast-2

# 禁用本地模式（使用 AWS）
export LOCAL_MODE=false
```

### 可选：使用 AWS Profile

```bash
# 使用特定的 AWS profile
export AWS_PROFILE=your-profile-name
```

## 三、测试方法

### 1. 快速连接测试

```bash
# 设置 Knowledge Base ID
export KNOWLEDGE_BASE_ID=your-kb-id

# 运行快速测试（通过应用 API 或直接调用 allergen_service）
# 方式一：通过 API（需应用运行）
# POST /api/allergens/extract  { "dish_name": "...", "description": "..." }
# 方式二：直接调函数
cd app
LOCAL_MODE=false KNOWLEDGE_BASE_ID=your-kb-id python -c "
from services import allergen_service as svc
r = svc.retrieve_context('peanut requirements')
print(r['engine'], len(r['chunks']))
"
```

### 2. 完整测试

```bash
# 本地模式测试（使用 docs/ 本地语料）
cd app
LOCAL_MODE=true python -c "
from services import allergen_service as svc
r = svc.retrieve_context('milk requirements')
assert r['engine'] == 'local'
print('local RAG OK:', len(r['chunks']), 'chunks')
"

# AWS 模式测试（需真实凭证）
export KNOWLEDGE_BASE_ID=your-kb-id
cd app
LOCAL_MODE=false python -c "
from services import allergen_service as svc
r = svc.retrieve_context('peanut requirements')
assert r['engine'] == 'aws'
print('aws RAG OK:', len(r['chunks']), 'chunks')
"
```

### 3. 单元测试

```bash
cd app
python -m unittest discover -s tests -p "test_*.py" -v   # 如 tests 存在
```

## 四、降级行为

RAG 服务会自动降级：

1. **AWS 模式**：`KNOWLEDGE_BASE_ID` 已设置 + `LOCAL_MODE=false`
   - 调用 Bedrock Knowledge Base `Retrieve` API
   - 返回 `{"engine": "aws", "chunks": [...]}`

2. **本地模式**：以下情况自动降级
   - `LOCAL_MODE=true`
   - `KNOWLEDGE_BASE_ID` 未设置
   - AWS 调用失败（权限、网络等）
   - 返回 `{"engine": "local", "chunks": [...]}`

3. **无结果**：没有找到相关内容
   - 返回 `{"engine": "none", "chunks": []}`

## 五、检查 Knowledge Base 状态

### 在代码中检查

```python
from services import allergen_service as svc

if svc.is_kb_available():
    print("将使用 AWS Knowledge Base")
else:
    print("将使用本地 docs/ 搜索")
```

### 使用 AWS CLI 检查

```bash
# 列出所有 Knowledge Bases
aws bedrock-agent list-knowledge-bases \
  --region ap-southeast-2

# 获取特定 Knowledge Base 详情
aws bedrock-agent get-knowledge-base \
  --knowledge-base-id YOUR_KB_ID \
  --region ap-southeast-2

# 测试检索
aws bedrock-agent-runtime retrieve \
  --knowledge-base-id YOUR_KB_ID \
  --retrieval-query '{"text": "peanut allergen requirements"}' \
  --region ap-southeast-2
```

## 六、常见问题

### 1. Knowledge Base 返回空结果

**可能原因**：
- Knowledge Base 还没有 ingestion
- 文档格式不支持
- 查询太模糊

**解决方法**：
```bash
# 检查 data source 状态
aws bedrock-agent list-data-sources \
  --knowledge-base-id YOUR_KB_ID

# 触发 ingestion job
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id YOUR_KB_ID \
  --data-source-id YOUR_DS_ID
```

### 2. 权限错误

**需要的 IAM 权限**：
```json
{
  "Effect": "Allow",
  "Action": [
    "bedrock:Retrieve",
    "bedrock-agent-runtime:Retrieve"
  ],
  "Resource": "arn:aws:bedrock:ap-southeast-2:*:knowledge-base/*"
}
```

### 3. 降级到本地模式

检查以下配置：
```python
import os

print(f"LOCAL_MODE: {os.environ.get('LOCAL_MODE', 'false')}")
print(f"KNOWLEDGE_BASE_ID: {os.environ.get('KNOWLEDGE_BASE_ID', '')}")
print(f"AWS_REGION: {os.environ.get('AWS_REGION', 'ap-southeast-2')}")
```

## 七、输出格式

### AWS 模式输出

```json
{
  "engine": "aws",
  "chunks": [
    {
      "text": "Peanuts must be declared...",
      "source": "s3://bucket/mpi-guide.pdf",
      "section": "",
      "score": 0.85
    }
  ]
}
```

### 本地模式输出

```json
{
  "engine": "local",
  "chunks": [
    {
      "text": "Peanuts must be declared on food labels...",
      "source": "nz_peal_allergens.md",
      "section": "Peanuts",
      "score": 1.0
    }
  ]
}
```
