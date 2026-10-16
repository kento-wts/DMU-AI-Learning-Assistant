# 任务管理前端 + 测试/交付 代码审查报告

| 项目 | 内容 |
| --- | --- |
| 审查日期 | 2026-10-16 |
| 审查分支 | `feat/task-ui-zyhh` |
| 基准提交 | `379b6e8 feat: make RAG ingestion idempotent`（与 `origin/feat/task-ui-zyhh` 同步） |
| 审查范围 | 全仓库：前端、后端、测试、配置 |
| 审查方式 | 只读审查（Git 状态、目录扫描、源码通读、关键词检索、环境探测） |
| 代码改动 | **无**。本次审查未修改任何业务代码、未重构、未新建数据库、未改动现有接口 |
| 执行的真实测试 | **0 个**（原因见 2.2、2.3） |

---

## 0. 审查范围与本次限制

本次为**只读审查**，遵守以下限制：

- 不修改业务代码、后端业务代码
- 不修改现有聊天消息格式、SSE 协议、公共 API、数据库结构
- 不安装任何新依赖、不自动格式化、不自动修复 lint/type
- 不删除文件、不使用 `git reset --hard` / `git clean` / `git push --force`
- 不为测试写入真实业务数据、不调用真实 DeepSeek API

所有验证命令均为只读或"失败即退出"（无副作用）。工作区审查前后均为 `clean`，变更文件数 0。

---

## 1. 当前实现

### 1.1 前端现状：单文件聊天界面，零分层

`frontend/src` 实际只有 3 个文件，**不存在** `components/`、`types/`、`services/`、`hooks/`、`pages/` 任何子目录：

| 文件 | 行数 | 内容 |
| --- | --- | --- |
| `frontend/src/App.tsx` | 327 | 唯一业务文件：UI + 状态 + fetch + 手写 SSE 解析全部内联 |
| `frontend/src/index.css` | 448 | 全量样式，含 Markdown 渲染样式与响应式媒体查询 |
| `frontend/src/main.tsx` | 10 | `createRoot` + `StrictMode` 挂载 |

外层配置：`frontend/package.json`(24)、`frontend/tsconfig.json`(20，`strict`/`noUnusedLocals`/`noUnusedParameters` 全开)、`frontend/vite.config.ts`(5，仅 react 插件)、`frontend/index.html`(12)。

**已实现的完整链路**：用户输入 → state → `sendQuestion` → `fetch` → SSE → message state → UI

- 状态：`question`(6)、`loading`(7)、`messages`(14)、`copiedMessageIndex`(15)；refs：`chatBoxRef`(17)、`abortControllerRef`(18)
- 类型：全项目**唯一**类型声明是组件内的局部类型 `type Message = { role: string; content: string }`（8-11 行）
- 函数：`App`(5)、`sendQuestion`(33-179)、`stopGeneration`(181-183)、`resetConversation`(185-192)、`copyAiMessage`(194-207)
- 网络：`fetch("http://127.0.0.1:8000/api/chat")`，地址**硬编码**在 62 行；无 env 读取、无 Vite proxy、无 API 抽象层
- SSE 消费：手动 `split("\n\n")` + 查找 `data:` 前缀 + 识别 `[DONE]` + `JSON.parse` 取 `{content}`/`{error}`（87-150）
- UI：乐观插入 user 消息 + 占位空 AI 气泡（content 为空时渲染返回 `null`），AI 侧用 `react-markdown` + `remark-gfm`，"AI正在思考..."提示，复制按钮，自动滚底
- 未实现：无路由、无状态管理、无会话持久化（`localStorage`/`sessionStorage`/`indexedDB` 关键词命中 0）

注：`resetConversation` 同时绑定"新建对话"与"清空对话"两个按钮（213-225），二者行为完全相同。

### 1.2 后端现状：2 条路由，RAG 已通，Agent/任务完全空白

`backend/main.py`（144 行）是唯一 API 入口，全部逻辑内联：

| 接口 | 位置 | 响应 |
| --- | --- | --- |
| `GET /api/hello` | main.py:129-131 | `{"message": "Hello, DMU AI!"}` |
| `POST /api/chat` | main.py:134-190 | `text/event-stream`（SSE 流式） |

`POST /api/chat` 内部函数：

| 函数 | 位置 | 职责 |
| --- | --- | --- |
| `_get_retriever` | 63-71 | 懒加载全局 `ChromaVectorStore` + `Retriever` 单例 |
| `Message` / `ChatRequest` | 74-80 | Pydantic 契约：`role: str`、`content: str`、`messages: list[Message]` |
| `_find_latest_user_message` | 83-89 | 逆序取最后一条 `role == "user"` |
| `_build_system_message` | 92-98 | `BASE_SYSTEM_PROMPT` + rag_prompt + `RAG_CONTEXT_NOTE`（含注入防护提示） |
| `_build_deepseek_messages` | 101-126 | system 置首，历史逐条追加，`role == "ai"` → `"assistant"` |
| `chat` | 135-141 | 端点主体：检索 → 拼 prompt → 返回 `StreamingResponse` |
| `generate`（闭包） | 147-181 | 调 DeepSeek 并按 SSE 逐块 yield |

**RAG 知识库链路（这部分是真实已实现的）**：

```
chroma_store.py      Chroma 持久化库，dir=<repo>/data/chroma，collection="knowledge_chunks"，cosine
vector_store.py      内存版向量库 + SearchResult / VectorRecord 类型（运行时未使用）
retriever.py         query → embed_text → store.search(top_k=3, metadata_filter 可选)
embedding.py         fastembed 懒加载，默认 "BAAI/bge-small-zh-v1.5"，双重检查锁
prompt_builder.py    纯文本模板：【知识库资料】[资料 N]... + 【用户问题】...
chunker.py           段落/句子感知切分，默认 1200 字符
pdf_loader.py        pypdf 抽取文本
ingest.py            抽取 → 切分 → embedding → replace_document，chunk ID = sha256(document_id\0index\0hash)（幂等）
ingest_document.py   CLI 导入单个 PDF，强制 --year / --major / --document-type
evaluate_retrieval.py + evaluation_dataset.json   检索诊断脚本（1 条人工标注 query）
documents/           10 个校规 PDF + .gitkeep
```

关键事实：**知识检索已能做到"检索 + 增强回答"，但检索结果对前端完全不可见**——`SearchResult.metadata/score` 只在服务端用于拼 prompt，SSE 只推送 `{content}` 纯文本，前端拿不到任何引用来源、文档名或相似度分数。

另有一处**未接线的并存实现**：`backend/rag_chat.py` 的 `RagChatService` 仅被 `backend/test_rag_chat.py` 引用，未接入 FastAPI。它与 `main.py` 在 RAG 注入位置（system vs user）、是否保留历史、`stream` 取值、是否带注入防护上都不一致。

### 1.3 本分支职责范围的实际状态

| 职责 | 状态 |
| --- | --- |
| 任务管理前端 | **未开始**，无任何文件/组件/类型 |
| 计划预览与用户确认 UI | **未开始** |
| 任务列表展示 | **未开始** |
| 任务状态展示/更新 UI | **未开始**，且后端无对应接口（前提不成立） |

### 1.4 结构化任务计划生成：确认不存在

核查证据：

- 全仓库大小写不敏感检索 `agent|due_date|deadline|todo|任务|计划|schedule` → **0 命中**
- 检索 `task|plan|agent|status` → 唯一命中是 `main.py:139` 的 HTTP `status_code=400`
- LLM 调用无结构化输出能力：无 `response_format`、无 JSON mode、无 `tools` / `function calling`（全后端仅 2 处 client 参数：`main.py:152` 的 `stream=True`、`rag_chat.py:69` 的 `stream=False`）
- 无数据库 / ORM：`backend/requirements.txt` 仅 7 项，唯一持久化是 Chroma 向量库；**不存在任务表**
- 无 `routers/`、`models/`、`schemas/`、`services/`、`db/` 任何目录

结论：**模型输出是自由 Markdown 文本，没有 JSON schema、没有 Task/Plan 对象、没有后续解析步骤。**

---

## 2. 验证结果

### 2.1 实际执行过的命令（全部只读）

| 命令 | 实际结果 |
| --- | --- |
| `Get-Location` | `C:\Users\zyhh2\DMU-AI-Learning-Assistant`，与要求路径一致 |
| `git branch --show-current` | `feat/task-ui-zyhh` |
| `git status` | `nothing to commit, working tree clean`；`--ignored --short` 空输出 |
| `git status --porcelain \| Measure-Object -Line` | 变更文件数 = **0**（每轮审查后复查，始终为 0） |
| `git log --oneline` / `git ls-files` / `git show --stat HEAD` | HEAD 仅动 `backend/knowledge/*`，无前端改动 |
| `Get-ChildItem -Recurse` | 目录树与文件清单，确认无 components/types/services/tests/docs/GitHub CI |
| `Get-Content` | 通读 App.tsx、main.tsx、index.css、package.json、tsconfig、vite.config、index.html、main.py、rag_chat.py、knowledge 全部模块 |
| `Select-String` | task/plan/agent/status/due_date/todo、response_format/tools、localStorage、rag_chat 引用、ChromaVectorStore 使用点等 |
| `Test-Path` | `pyproject.toml`/`pytest.ini`/`setup.cfg`/`conftest.py`/`Makefile`/`Dockerfile`/`.env.example`/`.github` **全部 False** |
| `npm run`、`npm run build`、`npm run lint`、`npm run test` | 四条**全部失败**（见 2.2） |
| `python -B -c "import fastapi, chromadb, ..."` | fastapi / uvicorn / openai / dotenv / pypdf / fastembed / chromadb / pytest **全部 MISSING** |
| 副作用复查 | `frontend/dist` False、`frontend/node_modules` False、`data/` False、`__pycache__` False、`.pytest_cache` False |

### 2.2 工具链实测结论（两个硬阻塞点）

**前端：`npm` 不存在。** PATH 上唯一的 `node` 是 Codex 自带运行时（`...\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe`，v24.19.0），该目录下只有 `node.exe`，无 `npm.cmd` / `npx.cmd`；`Get-Command npm` 无结果。四条命令输出逐字相同：

```
'npm' is not recognized as an internal or external command, operable program or batch file.
EXITCODE=1
```

失败发生在 shell 解析阶段，脚本内容从未被读取。另外 `frontend/package.json` 实际只有 3 个脚本：

```json
"scripts": { "dev": "vite", "build": "tsc && vite build", "preview": "vite preview" }
```

**`lint` 与 `test` 脚本不存在**——即使 npm 可用，这两个命令也只会得到 `Missing script`。`npm run build` 还需要 `tsc` / `vite` 本地二进制，而 `node_modules` 不存在、全局也无二者。

**后端：零依赖。** Python 3.13.9 存在（`D:\python\python.exe`），但 fastapi、uvicorn、openai、python-dotenv、pypdf、fastembed、chromadb、pytest **全部未安装**，也没有 `.venv`。embedding 模型本地缓存（`~/.cache/fastembed`、`~/.cache/huggingface`）不存在。

### 2.3 明确的「未验证」清单

**本次执行的真实测试数量 = 0。** 以下内容全部来自静态阅读，**不是**测试通过：

| 项目 | 状态 |
| --- | --- |
| 后端 pytest / unittest | **未执行**（依赖缺失；安装依赖在本阶段被禁止） |
| 后端服务启动 | **未执行**（缺依赖 + 缺 `DEEPSEEK_API_KEY`） |
| 前端 `npm run build` / `dev` / `preview` | **未执行**（缺 npm、缺 node_modules） |
| 前端渲染与交互 | **未验证**（无测试框架、无浏览器验证） |
| SSE 端到端联调 | **未验证**（需真实 DeepSeek 调用，被明令规避） |
| 知识库检索质量 | **未验证**（`evaluate_retrieval.py`、`test_retrieval_real.py` 均未运行；`data/chroma` 不存在，知识库为空） |
| embedding 模型可用性 | **未验证**（fastembed 未安装、模型未缓存） |
| 10 个 PDF 入库 | **未执行**（会写向量库 + 联网下载模型） |

**2.4 节列出的问题除注明外均为静态推断，未经运行验证；标注「待确认」处需环境就绪后用真实调用确认。**

### 2.4 静态审查发现的问题（仅记录，未修复）

**高优先级：**

1. **中止生成后残留空 AI 气泡**（`App.tsx:181-183` + 153-159 提前 `return`）：占位 `{role:"ai", content:""}` 永久留在 `messages` 中，UI 上被 237-239 行隐藏，但**下次发送时会随 payload 一起 POST**，后端会把它转成 `{"role":"assistant","content":""}` 送给 DeepSeek。是否被模型拒绝 → **待确认**（需真实调用）。
2. **后端对历史消息 role 无白名单**（`main.py:75` 的 `role: str` + 113-124 原样转发）：客户端可在历史中注入 `{"role":"system", ...}`，绕过 `main.py:92-98` 的受控 system 构造。`RAG_CONTEXT_NOTE` 只覆盖了资料侧注入。
3. **检索阶段异常无兜底**（`main.py:143-145` 位于 `try` 之外）：embedding 失败 / 维度不匹配 / 集合损坏 → 500 HTML；而只有 DeepSeek 调用被 `try` 包住（147-181），导致上游失败以 **HTTP 200 + SSE error 事件** 返回，状态码语义分裂。
4. **后端错误详情被前端吞掉**（`App.tsx:110-112` 抛出的真实 `data.error` 被 catch 统一覆盖为固定中文提示；`!response.ok` 时后端 400 的 `detail` 同样被丢弃）。
5. **`_get_retriever()` 无并发保护**（`main.py:63-71`）：端点是同步函数、跑在线程池中，两个并发首请求可能重复构造 `ChromaVectorStore`；对比 `embedding._get_model`（embedding.py:96）使用了 `_model_lock`。全项目无 shutdown 钩子调用 `store.close()`。
6. **无任何长度/成本护栏**：无消息条数上限、无字符上限、无 `max_tokens`；前端每次重发全量历史。
7. **元数据过滤能力闲置**：`ingest_document.py:52-67` 强制写入 `year` / `major` / `document_type`，但 `main.py:143` 既不传 `metadata_filter` 也不传 `top_k`，10 个 PDF 混在单一 collection `knowledge_chunks` 中。该能力在 `Retriever`(retriever.py:26) 与 `ChromaVectorStore.search`(chroma_store.py:217) 均已具备但未使用。

**中低优先级：**

8. **两套并存的 chat 实现**：`rag_chat.py` 未接入 FastAPI，与 `main.py` 语义不一致，误用会造成行为漂移。
9. **两套向量库实现**：`vector_store.py` 运行时未使用；`_validate_vector` 在 vector_store.py:115（返回 `int`）与 chroma_store.py:256（返回 `list[float]`）重复实现；`DEFAULT_TOP_K` 在 vector_store.py:10 与 retriever.py:13 重复定义。
10. **`ChromaVectorStore.close()` 后对象半废**（chroma_store.py:60-67）：`_collection` 置 `None`，后续调用抛 `AttributeError` 而非明确错误。
11. **`replace_document` 非原子**（chroma_store.py:130-136 已在 docstring 说明）：upsert 成功但 delete 失败会残留旧 chunk；无并发写保护。
12. **CORS 端口耦合**：后端白名单仅 `localhost:5173` / `127.0.0.1:5173`（main.py:41-44），Vite 若自动退到 5174 即被拦截。
13. **前端类型过松**：`role: string` 而非联合类型；`data` 使用 `as` 断言而非运行时校验（`App.tsx:105-108`）；React key 使用数组下标（241）。
14. **全局 CSS 选择器**：`button`(380-396)、`textarea`(344-368)、`h1`(78-84) 均无作用域，新增任务 UI 会继承这些样式。
15. **可访问性**：textarea 无 `label` / `aria-label`（290-310）；"AI正在思考..."无 `aria-live`（277-279）。
16. **测试可运行性问题**：
    - `backend/knowledge/test_retrieval_real.py` 实为调试脚本（只有 `main()`，无 test 函数），使用相对导入 `.chroma_store`（第 8 行）→ 直接 `python <file>` 会失败，须 `python -m`；且它构造默认 `ChromaVectorStore`（第 18 行）→ 在仓库根运行会创建 `data/chroma/`。
    - `backend/knowledge/test_embedding.py:70-83` 的 `ChineseSemanticSimilarityTests` **未打 patch 直接调用真实 `embed_text`** → 需 fastembed + 联网下载模型。**运行 pytest 前必须先确认这两处的隔离方式。**
17. **无测试 / Lint / CI 基础设施**：无 `pyproject.toml` / `pytest.ini` / `setup.cfg` / `conftest.py` / `Makefile` / `Dockerfile` / `.github`；前端无 `test` / `lint` 脚本、无 ESLint 配置。测试为 unittest 风格散落在源码目录，且使用 `from backend.xxx` 绝对导入（必须从仓库根运行）。
18. **模型与地址硬编码**：`main.py:150` 的 `deepseek-v4-flash` 与 `main.py:32` 的 base_url 均无法用环境变量覆盖。
19. **无知识库时静默降级**：空 collection → `search` 返回 `[]`（chroma_store.py:229-230）→ prompt 变为"没有检索到相关资料" → 仍然调用 DeepSeek。链路能通但输出无 grounding，联调时易误判为"检索失败"。
20. **缺配置即崩**：`main.py:23-26` 为模块级 `raise RuntimeError`，无自定义异常处理、无降级路径（例如无 key 时仍允许 `/api/hello` 探活）。

---

## 3. 待解决问题（影响全流程完成）

目标流程：**知识检索 → Agent 生成任务计划 → 用户预览/编辑 → 用户确认 → 保存任务 → 查看任务列表 → 更新任务状态**

逐环节缺口——**目前整条流程只有第 ① 环真实存在，其余全部缺失**：

| 环节 | 现状 | 缺什么 |
| --- | --- | --- |
| ① 知识检索 | 已实现且较完整（Chroma + fastembed + 分块 + 幂等入库） | 检索结果不回传前端（无来源/分数）；`metadata_filter` / `top_k` 未开放；知识库为空（10 个 PDF 未入库） |
| ② Agent 生成任务计划 | **完全不存在** | 无 agent 编排、无结构化输出（JSON schema）、无输出校验、无 `due_date`/优先级/步骤概念、无对应端点 |
| ③ 用户预览 / 编辑 | **不存在** | 前端无组件、无类型、无多视图结构（单文件 + 无路由） |
| ④ 用户确认 | **不存在** | 无确认交互、无"已确认"状态概念、无幂等提交保障 |
| ⑤ 保存任务 | **不存在** | **无任务持久化层**（无 DB、无表、无 ORM、无文件 store）。长期方案需负责人拍板 |
| ⑥ 查看任务列表 | **不存在** | 无列表接口、无列表组件 |
| ⑦ 更新任务状态 | **不存在** | 无状态枚举、无更新接口、无状态组件 |

跨环节的系统性阻塞：

1. **没有对话/任务的持久化与归属概念**：无会话 ID、无用户概念（README 将 auth 列为 Future），计划无法与某次对话或某个学生关联。
2. **接口契约未定型**：② 的 LLM 输出结构（字段名、是否含 `due_date`、步骤数上限）必须与 ⑤ 的存储结构、③⑥⑦ 的前端类型三者一致，否则返工。
3. **无前端 API 层**：唯一网络出口是 `App.tsx` 中硬编码的一行 `fetch`，新增任务 API 无处安放。
4. **无可用验证手段**：依赖全缺 + 无 lint/test 脚本 + 无 CI，新代码无法被自动验证；"基础测试"这项职责目前无落地入口。
5. **协议复用风险**：现 `/api/chat` 的 `role: "ai"` ↔ `"assistant"` 映射与手写 SSE 解析是隐性契约；任务接口若沿用同样的松类型或不加校验，会把问题一并复制。
6. **环境阻塞**：无 `.env.example`、无 venv 约定、无 npm → 任何人拿到仓库都无法启动，交付与演示都会卡住。

---

## 4. 开发建议

### 4.1 最少需要新增的文件

前端（全部为**新增文件**，避免改动队友文件）：

| 建议新增 | 作用 | 依赖 |
| --- | --- | --- |
| `frontend/src/types/task.ts` | `TaskPlan` / `PlanStep` / `Task` / `TaskStatus` 类型，作为前后端契约的单一真相源 | 无 |
| `frontend/src/services/taskApi.ts` | 任务相关 fetch 封装（含 base URL 集中管理） | 无 |
| `frontend/src/services/http.ts`（可选） | 公共 base URL / 错误处理 | 无 |
| `frontend/src/components/PlanPreview.tsx` | 计划预览（只读态） | types |
| `frontend/src/components/PlanEditor.tsx` | 计划可编辑态（增删步骤 / 改字段） | types |
| `frontend/src/components/PlanConfirmBar.tsx` | 确认 / 取消操作条 | types |
| `frontend/src/components/TaskList.tsx` + `TaskItem.tsx` | 任务列表与单项 | types |
| `frontend/src/components/TaskStatusSelect.tsx` | 状态展示 / 更新 | types |
| `frontend/src/components/task.css`（或 CSS Modules） | 任务 UI 样式，**避免复用全局 `button` / `textarea` 选择器** | 无 |

后端（**新增模块，不改现有接口**）：

| 建议新增 | 作用 |
| --- | --- |
| `backend/tasks/__init__.py` | 包 |
| `backend/tasks/schemas.py` | Pydantic 模型：计划请求/响应、任务、状态枚举 |
| `backend/tasks/store.py` | 持久化层（`sqlite3` 标准库或 JSON 文件，待定） |
| `backend/tasks/router.py` | `APIRouter`：生成计划 / 保存 / 列表 / 更新状态 |
| `backend/planner.py`（或 `backend/tasks/planner.py`） | 结构化计划生成：prompt + JSON 解析 + 校验 |
| `backend/tasks/test_*.py` | 沿用现有 unittest 风格 |

对现有文件的**最小必要改动**（各 1-3 行，风险可控）：`backend/main.py` 增加 `app.include_router(...)`；`frontend/src/App.tsx` 增加一个视图切换挂载点。

### 4.2 依赖情况

- **后端可以零新依赖**：`sqlite3`、`json`、`uuid`、`datetime`、`hashlib` 全在标准库；结构化输出可用"prompt 约束 JSON + `json.loads` + Pydantic 校验"实现，**不需要**升级 openai 版本或引入 langchain。
- **前端基础实现也可零新依赖**：用局部 state 做视图切换即可，不必上 react-router。
- **以下均为新依赖，必须审批**：`react-router-dom`（多视图）、`vitest` + `@testing-library/react` + `jsdom`（前端测试）、任何状态管理库。在"不安装任何新依赖"的限制下，建议先做零依赖版本。
- **环境层面**：Node + npm 与 Python 依赖的安装都是环境变更，需负责人确认。

### 4.3 冲突风险较高的位置

| 位置 | 风险 | 缓解建议 |
| --- | --- | --- |
| `frontend/src/App.tsx` | **最高**。唯一前端业务文件，聊天 UI 负责人大概率也在改 | 任务 UI 全部独立成组件，只在该文件加一个极小挂载点；改动前先与聊天 UI 负责人对齐 |
| `frontend/src/index.css` | 高。全局 `button` / `textarea` / `h1` 选择器会让新增任务 UI 继承样式，反向新增样式也可能改变聊天外观 | 用独立 CSS 文件 + 语义化 class 前缀（如 `.task-*`），不改动现有选择器 |
| `backend/main.py` | 中高。单文件内联全部逻辑，RAG 负责人也会改 | 只加 `include_router` 一行；生成计划逻辑放新模块 |
| `backend/knowledge/retriever.py`、`chroma_store.py` | 中。若计划生成需按专业/年级过滤知识（`metadata_filter`），会碰到 RAG 的检索调用 | 先不限流检索，做成"可选参数"并由 RAG 负责人接线 |
| `backend/rag_chat.py` | 低但危险。已有未接线的第二套实现 | 明确不继承、不复用，避免两条实现都活着 |
| 消息协议（`role` 字符串、SSE 格式） | 中。`ai` / `assistant` 的映射是隐性契约 | 新任务接口用严格枚举类型，不复用 `role: str` |

---

## 5. 下一步

### 5.1 需项目负责人先确定的事项（建议按此顺序）

1. **数据契约（最关键）**：`TaskPlan`、`PlanStep`、`Task`、`TaskStatus` 的字段名与取值集合；是否包含 `due_date`、优先级、预计耗时；计划步骤数上限。此项定下后，前端类型与后端 schema 可同时冻结。
2. **接口清单与路径**：是否采用 `POST /api/plan/generate`、`POST /api/tasks`、`GET /api/tasks`、`PATCH /api/tasks/{id}`；错误码与错误体约定（现 `/api/chat` 的 200 + error 事件模式是否延续）。
3. **持久化方案**：SQLite 文件 / JSON 文件 / 暂存内存三选一；文件落盘位置；"不新建数据库"是本阶段限制，正式开发时是否解除。
4. **计划生成是否允许一次真实 DeepSeek 调用**用于联调（当前被明令规避，导致 Agent 环节无法端到端验证）。
5. **检索是否需要回传引用来源**到前端（演示与可解释性），以及是否开放 `metadata_filter` 按专业/年级过滤。
6. **前端是否允许引入新依赖**（router / 测试框架），这决定 UI 结构是"条件渲染"还是"多路由"。
7. **环境与验证方案**：是否允许安装 Node/npm 与 Python 依赖；是否补充 `.env.example`；是否建立 lint/test/CI 入口（否则"基础测试"职责无法交付）。

### 5.2 建议的开发顺序（确认接口之后）

1. 先落**类型与 API 层**（`types/task.ts` + `services/taskApi.ts`），用本地 mock 数据驱动 UI——前端开发不阻塞在后端接口上，也符合职责说明中"任务状态 UI（如果后端接口已经存在）"的前提判断。
2. 再做**预览 → 编辑 → 确认**三个组件（演示主线）。
3. 然后**任务列表 + 状态更新**组件。
4. 后端并行推进 `schemas.py` → `store.py` → `planner.py` → `router.py`，先用 mock LLM 响应打通，最后才接真实 DeepSeek。
5. 最后接入 `App.tsx` 的单一挂载点，并补齐环境说明与演示材料。

---

## 附录 A：审查操作清单（可复现）

```powershell
# Git 状态
git rev-parse --show-toplevel; git branch --show-current; git status
git log --oneline -15; git ls-files; git show --stat HEAD
git status --ignored --short; git status --porcelain

# 目录与文件
Get-ChildItem -Recurse -Force | Select-Object Mode,Length,Name

# 关键词核查（task / plan / agent / 结构化输出 / 存储）
Select-String -Path backend\**\*.py -Pattern 'task|plan|agent|status|due_date|todo'
Select-String -Path backend\**\*.py -Pattern 'response_format|json_object|tool_choice|tools\s*='

# 配置探测
Test-Path pyproject.toml, pytest.ini, setup.cfg, conftest.py, Makefile, Dockerfile, .env.example

# 工具链探测（只 import，不联网、不建库）
npm run; npm run build; npm run lint; npm run test
python -B -c "import fastapi, chromadb, fastembed, pypdf, openai, pytest"
```

**注意**：`backend/knowledge/test_retrieval_real.py` 与 `backend/knowledge/test_embedding.py` 中的真实模型/真实向量库路径，运行前请先确认隔离方式（详见 2.4 第 16 条）。
