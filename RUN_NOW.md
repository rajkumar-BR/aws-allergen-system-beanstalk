# 🚀 立即运行！

AI 过敏原合规与菜单翻译系统——本地运行说明。

## 1. 当前状态

应用默认运行在 **真实 AWS 模式**（`LOCAL_MODE=false`）：
- 地址: http://localhost:8000
- 过敏原提取: **真实 Bedrock**（ap-southeast-2, Claude Opus 4.6）
- 法规 RAG: **真实 Bedrock Knowledge Base**（KB `CBFZTLLUHU`）
- 存储: **真实 DynamoDB + S3**（us-east-1）
- 翻译: **真实 Bedrock / Amazon Translate**

需要本机 `~/.aws/credentials` 有 IAM 长期凭证（`AKIA` 开头），且该用户有
Bedrock/DynamoDB/S3/Translate/Textract 权限。

## 2. 启动方式（Windows PowerShell）

```powershell
# 1) 设置分区域环境变量（推荐，一次性）
.\setup_aws_env.ps1

# 2) 启动应用
cd app
.\.venv\Scripts\python.exe application.py

# 3) 浏览器访问
#    http://localhost:8000
```

> 不用 AWS（本地模拟）：
> ```powershell
> $env:LOCAL_MODE = "true"
> cd app
> .\.venv\Scripts\python.exe application.py
> ```

## 3. 你会看到什么

### 🌈 彩色 UI 界面
- 左侧: Management & Upload（加载示例菜单 / 上传菜单文件 / 手动加菜）
- 右侧: 菜品卡片网格（点击卡片可人工审核/覆写过敏原）
- 顶栏: 显示语言切换（EN/ES/DE/JA/ZH）

### 🍽️ 16 个示例菜品
左侧 **Step 1 → "Load Sample Menu"**：
1. 从 `app/sample_data/sample_menu.json` 加载 16 道菜
2. 每道走完整管线：Bedrock 提取 → FSANZ 规则校验 → RAG 法规引用 → 4 语翻译 → DynamoDB 保存
3. 右侧显示彩色卡片（真实调用,约 4-5 分钟）

### 🏷️ 过敏原标签
每张卡片显示 `Contains Peanuts` / `Contains Milk` 等，附法规来源引用。

### 🥗 饮食筛选器
- Gluten-Free / Dairy-Free / Vegan（前端过滤）

## 4. 验证真实 AWS 调用

界面显示不等于在调 AWS，可用以下方式确认：

```powershell
# 1) 健康检查应显示 local_mode: false
Invoke-WebRequest http://localhost:8000/health

# 2) 触发一次真实提取，返回 engine 应为 bedrock-tool-use
$b = @{dish_name='Caesar Salad'; description='romaine, caesar dressing with anchovies, parmesan, croutons, egg'} | ConvertTo-Json
Invoke-WebRequest http://localhost:8000/api/allergens/extract -Method POST -Body $b -ContentType 'application/json'
```

- `engine: bedrock-tool-use` → 真实 Bedrock 调用 ✅
- `engine: rules` / `llm_source: offline` → 走了本地降级（凭证/权限/配额问题）

## 5. API 端点

```
GET  /health                        # 健康检查（含 local_mode 标志）
GET  /api/allergen-categories       # PEAL 过敏原分类（12 类）
GET  /api/languages                 # 支持的语言
POST /api/allergens/extract         # 过敏原提取（真实 Bedrock）
POST /api/compliance/verify         # 合规验证
GET  /api/menus/<menu_id>/items     # 菜单列表
POST /api/menus/<menu_id>/seed      # 加载 16 道示例菜（全链路）
POST /api/menus/<menu_id>/upload    # 上传菜单文件（Textract OCR）
PATCH /api/menus/<menu_id>/items/<item_id>   # 人工覆写过敏原
```

## 6. 两种运行模式

| 模式 | `LOCAL_MODE` | Bedrock/RAG/翻译 | 存储 | 用途 |
|---|---|---|---|---|
| 真实 AWS（默认） | `false` | 真实 AWS 服务 | DynamoDB + S3 | 完整功能、验证云端 |
| 本地模拟 | `true` | 规则引擎 + 本地 `docs/` | JSON 文件 | 离线开发/UI 调试（零成本） |

## 7. 故障排查

| 症状 | 原因/解决 |
|---|---|
| `engine: rules` 而非 bedrock 提取 | Bedrock 调用失败降级；查凭证、模型访问、配额 |
| `[Spanish - offline]` 翻译占位 | Bedrock/Translate 不可用 |
| DynamoDB ResourceNotFoundException | 表在 us-east-1；确认 `DYNAMODB_REGION=us-east-1` 且表存在 |
| `vectorSearchConfiguration ... not supported` | boto3 太旧；升级到 `boto3==1.43.88`（requirements.txt 已固化） |
| 端口占用 | `$env:PORT=8080` 后再启动 |

---

**现在就打开浏览器访问 http://localhost:8000 开始测试。**
提示：点击菜品卡片可查看过敏原详情、法规引用并进行人工审核。