# 本地可运行版本指南

本指南只针对**本地离线模式**（`LOCAL_MODE=true`，无需 AWS 连接）的开发和
UI 调试。**项目默认是真实 AWS 模式**（`LOCAL_MODE=false`），见
`README.md` / `RUN_NOW.md` / `setup_aws_env.ps1`。

---

## ✅ 核心功能测试通过

### 测试结果
| 功能模块 | 状态 | 详情 |
|----------|------|------|
| **过敏原提取** | ✅ 正常 | 关键词规则引擎 |
| **合规验证** | ✅ 正常 | PEAL 标准 1.2.3 |
| **RAG 检索** | ✅ 正常 | 本地 `docs/` 文档 |
| **Pipeline 整合** | ✅ 正常 | LLM + 规则 + RAG |

### 测试案例
```
Chicken Satay (花生酱+酱油) → 检测: Peanuts, Soybeans, Gluten(Wheat)
```

---

## 🚀 快速启动

### 选项1: 一行命令（Windows PowerShell）
```powershell
cd app
$env:LOCAL_MODE='true'; .\.venv\Scripts\python.exe application.py
```

### 选项2: 批处理脚本
```powershell
# 新建文件 run_local.bat
@echo off
cd /d %~dp0app
set LOCAL_MODE=true
.venv\Scripts\python.exe application.py
```

### 选项3: 运行本地脚本（仅 macOS/Linux）
```bash
# 项目根目录
./run_local.sh
```
> `run_local.sh` 是 bash 脚本，Windows 下不适用，请用选项 1/2。

---

## 🌐 访问本地应用

1. 应用启动后，打开浏览器
2. 访问: **http://localhost:8000**
3. 你会看到完整 UI，包括:
   - 彩色菜品卡片
   - 过敏原标签
   - 语言切换（英文+翻译）
   - 饮食筛选器（无麸质、无乳制品、素食）

---

## 📂 本地文件结构

```
app/
├── application.py          # 主应用 (14条路由)
├── services/
│   ├── allergen_service.py      # 你的核心模块 (✅)
│   ├── allergen_rules.py        # PEAL 规则引擎
│   ├── bedrock_service.py       # Bedrock 集成 (本地模式)
│   ├── dynamo_service.py        # DynamoDB (本地 JSON)
│   ├── s3_service.py           # S3 (本地目录)
│   └── textract_service.py     # OCR (本地解析)
├── static/                 # 完整 UI
├── sample_data/           # 16个示例菜品
└── docs/                  # RAG 本地文档库
```

---

## 🔧 核心功能演示

### 1. 加载示例菜单
- 点击 "Load Sample Menu"
- 16个菜品自动通过完整流程:
  - 过敏原提取（规则引擎）
  - 合规验证（PEAL 标准）
  - 翻译（本地占位符）

### 2. 查看过敏原标签
每个菜品卡片显示:
```
Peanuts | Soybeans | Gluten (Wheat)
Status: COMPLIANT
```

### 3. 人类审核
点击任意菜品 → 可以:
- 覆盖已确认的过敏原
- 删除菜品
- 查看合规详情

---

## 📊 技术细节

### 本地模式 (`LOCAL_MODE=true`)

| AWS 服务 | 本地替代 | 状态 |
|----------|----------|------|
| Bedrock | 规则引擎 + 关键词匹配 | ✅ |
| Knowledge Base | 本地 `docs/` 文档 | ✅ |
| Textract | 文本文件解析 | ✅ |
| S3 | 临时目录 | ✅ |
| DynamoDB | JSON 文件 | ✅ |

### API 端点
```
GET /health                    # 健康检查
POST /api/allergens/extract    # 过敏原提取
POST /api/compliance/verify    # 合规验证
POST /api/menus/seed          # 加载示例菜单
GET /api/allergen-categories   # PEAL 分类
```

---

## ⚡ 完整的端到端测试

运行完整流程:

```powershell
cd app
$env:LOCAL_MODE='true'; python -c "
import json
from services import allergen_service

# 完整过敏原管道
dish = 'Seafood Chowder'
desc = 'Creamy soup with fish, prawns and milk'

# 1. 提取
extraction = allergen_service.extract(dish, desc)
print('Extracted:', [a.name for a in extraction.allergens])

# 2. 合规
compliance = allergen_service.verify(dish, ['Fish', 'Crustacea', 'Milk'])
print('Compliance:', compliance.status)

# 3. RAG
rag = allergen_service.retrieve_context('fish requirements')
print('RAG Chunks:', len(rag['chunks']))

print('✅ All systems go!')
"
```

---

## 🛠️ 故障排除

### 1. 无法启动
```powershell
# 检查 Python 环境
python --version  # 需要 ≥3.11

# 安装依赖
pip install -r requirements.txt
```

### 2. 依赖问题
```powershell
# 清理并重新安装
rmdir /s .venv
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 端口占用
```powershell
# 修改端口
$env:PORT=8080
python application.py
```

---

## 🚀 下一步

### 转为真实 AWS 模式（本地调用 AWS）
1. 配置 AWS CLI（IAM 长期凭证，写入 `~/.aws/credentials`）
```powershell
aws configure
```

2. 设置分区域环境变量并启动
```powershell
# 一次性设置所有区域/资源名（推荐）
.\setup_aws_env.ps1

# 启动（LOCAL_MODE=false 即真实 AWS）
cd app
.\.venv\Scripts\python.exe application.py
```

### 部署到 AWS Elastic Beanstalk
```powershell
cd terraform
# 先看 DEPLOY_GUIDE.md（默认区域/模型/凭证要求）
terraform apply
```

---

**你的过敏原系统可以完全在本地运行（离线/真实 AWS 两种模式），准备就绪！**