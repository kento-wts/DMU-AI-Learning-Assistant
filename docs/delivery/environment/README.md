# 环境说明

> **状态：待补。** 本文件目前只记录审查阶段**实测确认**的环境事实，安装与启动步骤需等负责人确认安装授权后补齐。

---

## 1. 技术栈

| 层 | 技术 | 来源 |
| --- | --- | --- |
| 前端 | React 19.1 + TypeScript 5.8 + Vite 6.3 | `frontend/package.json` |
| 后端 | FastAPI + Uvicorn（Python） | `backend/requirements.txt` |
| 向量库 | ChromaDB（本地持久化） | `backend/knowledge/chroma_store.py` |
| Embedding | fastembed `BAAI/bge-small-zh-v1.5`（本地运行，无 API Key） | `backend/knowledge/embedding.py:20` |
| 大模型 | DeepSeek `deepseek-v4-flash` | `backend/main.py:150` |

## 2. 依赖清单

| 前端 | 版本 |
| --- | --- |
| react / react-dom | ^19.1.0 |
| react-markdown | ^10.1.0 |
| remark-gfm | ^4.0.1 |
| vite | ^6.3.5 |
| typescript | ~5.8.3 |

| 后端 | 约束 |
| --- | --- |
| fastapi / uvicorn / openai / python-dotenv | 无版本约束 |
| pypdf | >=6.0,<7.0 |
| fastembed | >=0.6,<1.0 |
| chromadb | >=1.0,<2.0 |

## 3. 环境变量

| 变量 | 必需 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | **是** | `backend/main.py:23-26` 模块级校验，缺失时后端**无法导入**，直接抛 `RuntimeError` |
| `EMBEDDING_MODEL` | 否 | 覆盖默认 embedding 模型名（`embedding.py:21`） |
| `EMBEDDING_CACHE_DIR` | 否 | 覆盖 embedding 模型缓存目录（`embedding.py:22`） |

仓库内**不存在** `.env`，也**不存在** `.env.example`（`.gitignore` 已忽略 `.env` 与 `.env.*`，但保留 `!.env.example`）。

## 4. 启动方式

### 4.1 后端（已实测通过，2026-10-16）

```bash
# 1) 建立独立虚拟环境（.venv 已被 .gitignore 覆盖）
python -m venv .venv

# 2) 安装声明依赖（未新增任何新包）
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

# 3) 配置密钥后启动（从仓库根运行，backend/main.py 使用相对导入）
$env:DEEPSEEK_API_KEY = "<your-key>"
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

实测结果：`Application startup complete.`，就绪约 **3.5 秒**；`GET /api/hello` 返回 `200` + `{"message":"Hello, DMU AI!"}`。

**注意**：`DEEPSEEK_API_KEY` 只需非空即可启动（模块级校验只判断是否存在），因此做接口验证时可用占位值；但一旦请求 `/api/chat` 的成功路径就会真实调用 DeepSeek。

### 4.2 前端（已实测通过，2026-10-16）

系统未安装 Node.js / npm，本轮改用**官方 ZIP 版**解压到临时目录（不写注册表、无需管理员权限、可随时删除）：

```powershell
# 1) 取官方 ZIP（约 36 MB）并解压到 %TEMP%
$dest = Join-Path $env:TEMP 'dmu-node'
# 版本索引：https://nodejs.org/dist/index.json  -> 选 lts 字段非 false 的版本
# 下载：https://nodejs.org/dist/v24.22.0/node-v24.22.0-win-x64.zip
Expand-Archive -Path "$dest\node-v24.22.0-win-x64.zip" -DestinationPath $dest

# 2) 加入当前会话 PATH
$nodeDir = "$dest\node-v24.22.0-win-x64"
$env:Path = "$nodeDir;$env:Path"

# 3) 安装依赖：用 ci 而不用 install，避免改写被跟踪的 package-lock.json
cd frontend
npm ci --no-audit --no-fund

# 4) 类型检查与构建
npx tsc --noEmit
npm run build

# 5) 开发服务器
npm run dev      # 或：node node_modules/vite/bin/vite.js --port 5173 --strictPort
```

实测结果：`npm ci` 装 166 个包 / 14 秒且 lockfile 零改动；`tsc --noEmit` **零类型错误**；`npm run build` 281 模块 / 941ms；dev server `GET /` 返回 **200**。

**实测注意**：`npm run build` 与 `npm run dev` 在**受限沙箱内会失败**（esbuild 报 `Cannot read directory "../..": Access is denied.`，因为它要读取仓库的上级目录）。这不是项目缺陷，在正常权限的终端里可正常运行。

### 4.3 端口与 CORS（已实测）

前端请求地址硬编码为 `http://127.0.0.1:8000/api/chat`（`frontend/src/App.tsx:62`）；后端 CORS 白名单为 `http://localhost:5173` 与 `http://127.0.0.1:5173`（`backend/main.py:41-44`）。

实测证实：`Origin: http://localhost:5173` 的预检请求返回 `200` 且带 `access-control-allow-origin`；`Origin: http://127.0.0.1:5174` 返回 `400 Bad Request` 且**无**该响应头。**Vite 端口必须是 5173，否则前端请求会被 CORS 拦截。**

## 5. 数据落盘位置

| 路径 | 内容 | 是否入库 git |
| --- | --- | --- |
| `<repo>/data/chroma` | Chroma 向量库（`chroma_store.py:16`） | 否（`.gitignore` 忽略 `data/chroma/`） |
| 仓库根 `frontend/dist` | 前端构建产物 | 否 |
| `fastembed` 默认缓存目录 | embedding 模型权重 | 否 |

## 6. 环境实测状态（2026-10-16 更新）

### 6.1 已解决

| 项 | 处理与结果 |
| --- | --- |
| `python --version` | `3.13.9`（`D:\python\python.exe`），pip 25.2 |
| 后端依赖 | **已安装到 `.venv`**：fastapi 0.143.3、uvicorn 0.54.0、openai 3.31.0、python-dotenv 1.2.4、pypdf 6.21.0、fastembed 0.9.0、chromadb 1.5.9 |
| 后端测试 | **87/87 通过**（`python -m unittest discover -s backend -t .`） |
| 后端启动 | **已跑通**（需配置 `DEEPSEEK_API_KEY`，占位值即可启动） |
| embedding 模型 | **已下载并可用**（`BAAI/bge-small-zh-v1.5`，首次约 28 秒） |
| `data/chroma` | **已创建**，含《…竞赛列表(2026年)》9 个 chunk（`chroma.sqlite3` 约 418KB） |
| 知识检索 | **已实测**：q1 的 4 个人工标注竞赛名 4/4 命中，最高相似度 0.6837 |
| 真实 DeepSeek 端到端 | **已跑通**（见 6.1.1） |

### 6.1.1 真实 DeepSeek 端到端验证（2026-10-16）

使用真实 `DEEPSEEK_API_KEY` 启动真实后端 + 真实 dev server，由 Playwright 驱动系统 Edge 走完整链路：

| 项目 | 实测结果 |
| --- | --- |
| 直接 POST 真实 RAG 问题 | HTTP 200；535 个 content 事件 / 0 个 error / 1 个 `[DONE]` |
| RAG 是否生效 | 回答中明确出现"依据：**资料3**中列有…"，引用知识库资料编号 |
| RAG 约束性 | 提问知识库未覆盖的主题（奖学金评定），模型回答"资料未包含…因此无法据此说明"，**未编造** |
| 前端真实流式 | 聊天区字符数 37 → 92 递增，回答正常渲染 |
| 真实回答复制 | 剪贴板内容与消息内容完全一致 |
| 后端日志 | 无 Traceback / 500 / Exception |

**关于 API key 的安全约定**：密钥**只通过进程环境变量传入**，未写入仓库任何文件（已用全文检索确认仓库内不含该 key 字符串）。仓库至今**没有 `.env` / `.env.example`**；若后续要固化，建议只提交 `.env.example` 占位文件并把 `.env` 保留在本地。

### 6.2 曾经阻塞、现已解决

| 项 | 处理结果 |
| --- | --- |
| Node.js / npm | 系统确实**完全不存在** npm（`node v24.19.0` 来自 Codex 自带运行时；`C:\Program Files\nodejs`、nvm / fnm / volta / scoop 全无；`winget` / `choco` / `scoop` 均不可用，仅剩 `msiexec`）。**改用 `%TEMP%` 下的官方 ZIP 版解决** |
| `npm run` / `build` | 之前 4 条全部失败（`'npm' is not recognized`）；现 `npm ci` / `tsc` / `build` / `dev` 均通过 |
| `frontend/node_modules` | 已由 `npm ci` 创建（166 包），被 `.gitignore` 覆盖 |
| 前端验证 | 已完成构建 + 真实浏览器检查（20 项） |

### 6.3 仍然阻塞或未验证

| 项 | 实测结果 |
| --- | --- |
| 系统级 Node.js | 未安装。当前依赖 `%TEMP%` 的临时解压，**临时目录被清理后需重下**。长期开发建议正式安装 |
| 真实 DeepSeek 调用 | **已完成**（见 6.1.1）。注意：密钥需由负责人保管，已用密钥应尽快吊销 |
| 知识库完整性 | 仅入库 1/10 个 PDF |
| 中文输入法回车（FE-04） | 未验证（headless 无法触发 `isComposing`） |
| `frontend/package-lock.json` | 刻意保持零改动（选用 `npm ci`） |

### 6.4 embedding 缓存的坑（实测发现）

| 事项 | 实测表现 |
| --- | --- |
| 缓存位置 | `C:\Users\zyhh2\AppData\Local\Temp\fastembed_cache` —— **在系统临时目录内**，可能被清理工具删除，届时需重新下载 |
| 覆盖方式 | 设置 `EMBEDDING_CACHE_DIR`（`backend/knowledge/embedding.py:22`）可改到稳定目录 |
| 符号链接 | `huggingface_hub` 警告无法创建 symlink（需开发者模式或管理员），缓存以"降级模式"存储、占用更多磁盘 |
| 下载限流 | 未配置 `HF_TOKEN` 时提示 `You are sending unauthenticated requests to the HF Hub`，速率受限 |
| 无网络时 | 测试报 `ValueError: Could not load model BAAI/bge-small-zh-v1.5 from any source.` → 包装为 `EmbeddingError`，导致 `discover` 出现 1 个错误 |

### 6.5 本轮产生的本地产物（均在 .gitignore 覆盖范围内，不影响 git 状态）

| 路径 | 说明 | 可否删除 |
| --- | --- | --- |
| `.venv/` | 独立虚拟环境（`.gitignore:5`） | 可删，删后需重装依赖 |
| `data/chroma/` | 向量库（`.gitignore:8`），含 1 个文档的 9 个 chunk | 可删，属本地知识库数据 |
| `backend/__pycache__/`、`backend/knowledge/__pycache__/` | 字节码缓存（`.gitignore:3`），即使加 `-B` 仍被创建 | 可删 |
| `frontend/node_modules/` | `npm ci` 安装的 166 个包 | 可删，删后需重装 |
| `frontend/dist/` | 生产构建产物 | 可删，删后重新 `npm run build` |
| `%TEMP%\dmu-node\`、`%TEMP%\dmu-harness\` | 临时 Node.js 运行时与测试脚本（**在仓库之外**，不入 git） | 可删 |

## 7. 待补内容

- [x] 依赖安装步骤（后端见 4.1，前端见 4.2）
- [x] 启动验证记录（后端见 4.1 与测试表 6.2；前端见 4.2 与测试表第 7 节）
- [x] 知识库入库步骤（单个文档已完成，见测试表 6.3）
- [x] 常见报错与排查（见 6.4；另见 4.2 的 esbuild 沙箱限制说明）
- [x] 前端依赖安装与启动（已用 `%TEMP%` 下的 ZIP 版 Node.js 完成）
- [ ] `.env` 或 `.env.example` 的建立方式（需负责人确认；属新增文件，涉密需谨慎）
- [ ] 剩余 9 个 PDF 的入库元数据方案（year / major / document_type 取值需 RAG 负责人确定）
- [ ] 全量入库后的检索质量评估（`evaluate_retrieval` 扩展数据集）
- [ ] 系统级安装 Node.js（当前依赖临时解压，长期开发建议正式安装）
- [x] 真实 DeepSeek 端到端验证（已用负责人提供的密钥完成）
- [ ] 密钥保管方式与吊销流程（**建议：已暴露的 key 应尽快吊销重发**）

