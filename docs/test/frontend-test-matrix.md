# 测试用例表（任务管理前端 + 集成 + 后端回归）

| 项目 | 内容 |
| --- | --- |
| 日期 | 2026-10-16 |
| 分支 | `feat/task-ui-zyhh` |
| 基准提交 | `9c3334f`（审查报告入库后） |
| 本轮执行结果 | **后端全部实测通过**（87/87，见 6.1-6.4）；**前端构建成功并通过 20 项真实浏览器检查**（见第 7 节）；**真实 DeepSeek 端到端链路已跑通**（见 7.6）。发现 1 个真实缺陷（FE-08，上游后果经实测为良性） |
| 实测环境 | 后端：仓库内 `.venv`（Python 3.13.9 + `requirements.txt` 声明的 7 项，未新增包，用标准库 `unittest`）。前端：`%TEMP%` 下的 Node.js 官方 ZIP 版 v24.22.0 + npm 11.19.1（未做系统级安装）+ `npm ci` 安装的 166 个声明依赖 |
| 浏览器验证方式 | Playwright 1.62.1 驱动**系统自带 Edge**（未下载浏览器）；后端替换为**与 `backend/main.py` SSE 契约完全一致的本地 mock**，因此**未调用真实 DeepSeek、未消耗任何额度** |
| 填表约定 | 只记录**真实执行过**的结果；没跑过的一律填「未执行」，禁止把"看起来没问题"填成「通过」 |

---

## 1. 结果取值与通过口径

| 取值 | 含义 |
| --- | --- |
| 未执行 | 尚未运行（默认值） |
| 通过 | 已运行且结果与预期一致，附证据（截图/日志/命令输出） |
| 失败 | 已运行且结果与预期不符，附实际现象 |
| 阻塞 | 因环境或依赖缺失无法运行，需先解决前置条件 |
| 待确认 | 需要负责人先决策（如是否允许真实 API 调用）才能执行 |

**通过口径**：必须留下可复现证据（命令 + 输出，或浏览器截图 + 操作步骤），仅口头描述不算通过。

---

## 2. 环境前置用例

| 编号 | 用例 | 前置条件 | 步骤要点 | 预期结果 | 执行方式 | 结果 |
| --- | --- | --- | --- | --- | --- | --- |
| ENV-01 | Node 与 npm 可用 | 无 | `node --version`、`npm --version` | 两条均返回版本号 | 命令行 | **通过（临时方案）**。系统仍无 npm（`C:\Program Files\nodejs`、nvm / fnm / volta / scoop 均不存在，`winget` / `choco` / `scoop` 不可用）。改用官方 ZIP 版解压到 `%TEMP%\dmu-node\node-v24.22.0-win-x64`：node v24.22.0（LTS Krypton）+ npm 11.19.1，**不写注册表、无需管理员权限、可随时删除** |
| ENV-02 | 前端依赖就绪 | ENV-01 通过 | `npm ci` | 安装成功且不修改 lockfile | 命令行 | **通过**。`npm ci` 安装 166 个包、耗时 14 秒；`git status package-lock.json` 改动数 **0**（刻意选用 `npm ci` 而非 `npm install`，因为它只按 lockfile 安装、绝不改写 `package-lock.json`） |
| ENV-03 | 后端依赖就绪 | 无 | `.venv\Scripts\python.exe -m pip install -r backend\requirements.txt` | 7 项依赖导入成功 | 命令行 | **通过**。已建 `.venv` 并安装：fastapi 0.143.3、uvicorn 0.54.0、openai 3.31.0、python-dotenv 1.2.4、pypdf 6.21.0、fastembed 0.9.0、chromadb 1.5.9 |
| ENV-04 | DeepSeek 密钥配置 | 无 | 检查 `.env` 中 `DEEPSEEK_API_KEY` | 变量存在且非空 | 命令行 | **部分验证**。模块级校验只要求非空，用占位值即可成功启动；真实密钥仍未配置，故未做任何真实模型调用 |
| ENV-05 | 知识库已入库 | ENV-03 通过 | `python -m backend.knowledge.ingest_document <pdf> --year .. --major .. --document-type ..` | 10 个 PDF 入库 | 命令行 | **部分通过（1/10）**。仅入库评估数据集对应的《…竞赛列表(2026年)》→ 9 chunks。其余 9 个 PDF 未入库（year / major / document_type 取值属 RAG 负责人决策） |
| ENV-06 | 测试隔离确认 | 无 | 确认真实模型 / 真实向量库路径的隔离方式 | 无仓库内意外写入 | 命令行 + 静态检查 | **已确认**。11 个 mock 模块全部使用临时目录；`test_retrieval_real.py` 无双亲包时直接运行会 `ImportError`、作为包模块导入时含 0 个 test 函数（不执行 `main()`，不产生写入）；`test_embedding.py` 的真实模型测试确认会联网下载模型 |
| ENV-07 | CORS 端口匹配 | ENV-03 通过 | 后端启动后发预检请求 | 5173 放行、其他端口拦截 | 命令行 | **后端侧通过**。实测 Origin=5173 预检 `200` 且带 `access-control-allow-origin`；Origin=5174 预检 `400` 且**无**该响应头。前端侧仍因无 npm 未验证 |

---

## 3. 前端聊天功能回归用例（改动 `App.tsx` 前后都必须跑）

> 说明：这些用例覆盖的是**现有功能**。它们目前的目的是"防回归"——一旦抽取组件（见组件梳理 A 类）就必须重跑。

| 编号 | 用例 | 前置条件 | 步骤要点 | 预期结果 | 结果 |
| --- | --- | --- | --- | --- | --- |
| FE-01 | 发送普通问题 | mock 后端 + dev server | 输入文字，按 Enter | 用户气泡即时出现，"AI正在思考..."可见，随后流式输出 | **通过**。用户气泡即时渲染；思考提示在首块（1.2s 后）到达前**被捕获到**；内容长度 23 → 27 字符递增，确认增量拼接 |
| FE-02 | 回车发送 | 同上 | 输入后按 Enter | 发送，且 textarea 不换行 | **通过**。请求数 0 → 1 |
| FE-03 | Shift+Enter 换行 | 同上 | 输入后按 Shift+Enter | 换行，不发送 | **通过**。textarea 值变为 `"第一行\n第二行"`，请求数仍为 0 |
| FE-04 | 中文输入法回车 | 同上 | 中文输入法组字状态下按 Enter | 仅确认候选词，**不发送** | **未验证**。headless 浏览器无法真实触发输入法组字（`isComposing`），需人工在中文输入法下确认。`App.tsx:301` 的判断逻辑仍在，静态上正确 |
| FE-05 | 空输入拦截 | 同上 | 输入纯空格后点发送 | 不发送、无请求发出 | **通过**。气泡数 0、请求数 0 |
| FE-06 | 发送中互斥 | 同上 | 生成过程中再次发送 | 第二次发送不产生新请求（`loading` 守卫） | **通过**。生成中连按 4 次 Enter，请求数仍为 **1**；按钮正确显示"停止生成" |
| FE-07 | 停止生成 | 同上 | 生成中点"停止生成" | 流中断，按钮恢复为"发送" | **通过**。按钮由"停止生成"回到"发送"；另实测**输入框保留原文**（因此停止后再按 Enter 可重发同一问题，属设计行为） |
| FE-08 | 停止后残留空气泡 | FE-07 通过 | 在**首个数据块到达前**停止生成，再发一条新问题，抓取请求体 | 请求体中的 `messages` 应只含有效消息 | **发现缺陷（已复现）**。请求体实测为 `["user:5","ai:961","user:13","ai:0","user:10"]`，其中 **`ai:0` 即中止时残留的空 AI 消息被带入下一次请求**。该空气泡在 DOM 上因 `App.tsx:237-239` 被隐藏（用户无感），但状态里确实存在 |
| FE-09 | 清空 / 新建对话 | 同上 | 点击"清空对话" | 消息与输入框清空 | **通过**。气泡数归 0、输入框为空 |
| FE-10 | 复制 AI 回答 | 同上 | 点击气泡右下"复制" | 剪贴板内容正确，按钮变"已复制" | **通过**。按钮文案变为"已复制"；剪贴板实测为 `"你好！这是**模拟**流式回答。..."`，与回答内容一致 |
| FE-11 | Markdown 渲染 | 同上 | 让 AI 返回含标题/列表/表格/代码块的回答 | 各元素正确渲染 | **通过**。`<strong>` / `<h2>` / `<li>` / `<table>` / `<pre>` / `<code>` 六类元素全部出现 |
| FE-12 | 自动滚底 | 同上 | 长回答导致聊天区溢出 | 新消息出现时自动滚到底部 | **通过（附一处轻微瑕疵）**。溢出场景下最新消息与复制按钮**均完整可见**；但滚动余量稳定停在 **25px**（等待 2 秒不收敛），落在容器内边距范围内。推断原因：`scrollTo` 目标 `scrollHeight` 取自 effect 执行时刻，内容后续又长高 25px，且 `behavior:"smooth"` 不再触发新动画 |
| FE-13 | 请求失败提示 | 拦截 `/api/chat` 使其失败 | 发送问题 | 显示"请求失败，请检查网络连接或稍后重试。" | **通过**。界面显示该文案 |
| FE-14 | 窄屏布局 | 视口 700×800 | 窗口宽度 < 760px | 侧栏堆叠在顶部，气泡最大宽度 80%，聊天区高度 55vh | **通过**。`flex-direction: column`、侧栏 `flex-basis: auto`（宽 658px = 94%）、聊天框内容高 440px（=55vh）、气泡 `max-width: 80%` |

---

## 4. 任务管理 UI 用例（**依赖开发完成，当前无对应实现**）

| 编号 | 用例 | 对应流程环节 | 预期结果 | 结果 |
| --- | --- | --- | --- | --- |
| TASK-01 | 计划预览渲染 | ③ | Agent 返回的计划正确渲染为可读步骤列表 | 未执行（功能未开发） |
| TASK-02 | 计划步骤编辑 | ③ | 修改步骤标题/描述后，本地状态同步更新 | 未执行 |
| TASK-03 | 步骤增 / 删 / 排序 | ③ | 列表项正确增减，顺序可调整 | 未执行 |
| TASK-04 | 编辑后取消 | ③ | 放弃修改，回到预览初始态，不产生提交 | 未执行 |
| TASK-05 | 用户确认提交 | ④ | 仅确认后触发保存；重复点击不重复创建（幂等） | 未执行 |
| TASK-06 | 保存失败回滚 | ⑤ | 保存接口失败时给出明确提示，不静默丢弃 | 未执行 |
| TASK-07 | 任务列表渲染 | ⑥ | 按状态/时间正确展示，字段完整 | 未执行 |
| TASK-08 | 空列表态 | ⑥ | 展示空态占位而非空白页 | 未执行 |
| TASK-09 | 状态更新 | ⑦ | 切换状态后立即回显，刷新后仍为更新后的值 | 未执行 |
| TASK-10 | 状态更新失败 | ⑦ | 接口失败时回滚到原状态并提示 | 未执行 |
| TASK-11 | 长计划滚动 | ③⑥ | 步骤数很多时容器可滚动且不撑破布局 | 未执行 |
| TASK-12 | 窄屏下任务 UI | ③⑥⑦ | 与聊天界面一致的响应式表现 | 未执行 |

---

## 5. 前后端集成用例

| 编号 | 用例 | 前置条件 | 步骤要点 | 预期结果 | 结果 |
| --- | --- | --- | --- | --- | --- |
| INT-01 | SSE 事件格式 | **真实后端 + 真实 DeepSeek** | 请求 `/api/chat` | 事件为 `data: {"content": ...}\n\n`，结束为 `data: [DONE]\n\n` | **通过（真实链路）**。HTTP 200；**535 个 content 事件、0 个 error、1 个 `[DONE]`**；原始字节格式逐字符合契约 |
| INT-02 | role 映射 | 真实后端 | 观察发给上游的 messages | 前端 `role:"ai"` 映射为 `"assistant"`，历史顺序不变 | **通过**。`backend/test_main.py` 字符串断言覆盖（已通过）；真实链路中带空的 `ai` 消息的请求也正常送达并返回 |
| INT-03 | 无 user 消息 | 真实后端 | POST 只含 `ai` 的消息 | 返回 400 `{"detail":"请求中没有 user 消息"}` | **通过（真实后端）**。实测 400 + 该 detail |
| INT-04 | 上游失败提示 | 真实后端 | 触发上游错误 | 前端展示失败文案 | **部分验证**。网络失败路径已通过浏览器验证（FE-13）；**SSE `error` 事件路径未验证**，且后端真实错误详情被前端泛化文案覆盖的可观测性问题仍在 |
| INT-05 | 检索阶段异常 | 真实后端 | 用不存在的 embedding 模型 | 应有结构化错误 | **已证实为缺陷**。实测返回 **HTTP 500 + 纯文本 `Internal Server Error`**，服务端日志为未捕获的 `EmbeddingError` |
| INT-06 | 知识库为空 | 真实后端 | 不入库任何文档直接提问 | 链路可通，prompt 回落为"当前知识库没有检索到相关资料" | **通过**。空 collection 时 `search` 返回 `[]`，链路不报错 |
| INT-07 | 引用来源可见性 | 真实后端 | 提问命中知识库 | 检索来源是否回传前端 | **已确认不可见**。真实回答中出现"依据：**资料3**中列有…"——说明检索内容**确实进入了 prompt 并影响回答**，但前端拿不到来源元数据与相似度分数。是否改造待负责人决策 |
| INT-08 | 长历史 token 增长 | 真实后端 | 连续多轮对话 | 是否有长度护栏 | **未验证**（仅发 3 轮，未做长历史压力测试）。代码层面确认无任何长度护栏 |
| INT-09 | 真实 RAG 回答质量 | 真实后端 | 用评估数据集 q1 同主题提问 | 回答基于知识库且不越界 | **通过**。提问 A 类竞赛 → 回答引用「资料1/资料3」并列出华为ICT大赛等；提问奖学金评定 → 模型明确回答"知识库资料未包含奖学金评定办法，因此无法据此说明"，**证明 RAG 生效且模型被约束在知识库范围内**（未编造） |

---

## 6. 后端回归用例（现有 13 个测试文件）

| 测试文件 | 行数 | 特征 | 可安全运行 | 说明 |
| --- | --- | --- | --- | --- |
| `backend/test_main.py` | 213 | 全 mock，含 SSE 格式断言 | 是（需依赖） | 自设 `DEEPSEEK_API_KEY=test-key`，全程 patch `client` 与 `_get_retriever` |
| `backend/test_rag_chat.py` | 164 | 全 mock | 是（需依赖） | 覆盖未接线的 `RagChatService` |
| `backend/knowledge/test_chroma_store.py` | 200 | 使用临时目录 | 是（需依赖） | 不写仓库 `data/` |
| `backend/knowledge/test_chunker.py` | 28 | 纯函数 | 是（需依赖） | 无 IO |
| `backend/knowledge/test_embedding.py` | 64 | **含真实模型测试** | **需隔离** | `ChineseSemanticSimilarityTests`(70-83) 直接调用真实 `embed_text`，需 fastembed + 联网下载模型 |
| `backend/knowledge/test_ingest.py` | 79 | patch `embed_text` | 是（需依赖） | 临时文件 |
| `backend/knowledge/test_ingest_document.py` | 186 | patch + 临时目录 | 是（需依赖） | —— |
| `backend/knowledge/test_ingest_pipeline.py` | 431 | patch + 临时目录 | 是（需依赖） | 最大的测试文件 |
| `backend/knowledge/test_pdf_loader.py` | 78 | 临时文件 | 是（需依赖） | —— |
| `backend/knowledge/test_prompt_builder.py` | 56 | 纯函数 | 是（需依赖） | —— |
| `backend/knowledge/test_retriever.py` | 117 | patch `embed_text` | 是（需依赖） | —— |
| `backend/knowledge/test_vector_store.py` | 85 | 纯内存 | 是（需依赖） | 运行时未使用的实现 |
| `backend/knowledge/test_retrieval_real.py` | 33 | **非测试脚本** | **不可当测试跑** | 只有 `main()`，无 test 函数；相对导入，须 `python -m`；构造默认 `ChromaVectorStore` **会在仓库根创建 `data/chroma/`** |

**统一结果：全部通过（87/87）。** 本轮已在 `.venv` 中安装 `requirements.txt` 声明的依赖并实际运行，**未修改任何测试文件**，测试框架使用标准库 `unittest`（未安装 pytest）。

### 6.1 模块级实测结果

| 模块 | 用例数 | 结果 |
| --- | --- | --- |
| `backend.test_main` | 7 | 通过 |
| `backend.test_rag_chat` | 11 | 通过 |
| `backend.knowledge.test_chunker` | 6 | 通过 |
| `backend.knowledge.test_prompt_builder` | 9 | 通过 |
| `backend.knowledge.test_vector_store` | 11 | 通过 |
| `backend.knowledge.test_retriever` | 8 | 通过 |
| `backend.knowledge.test_chroma_store` | 8 | 通过 |
| `backend.knowledge.test_ingest` | 3 | 通过 |
| `backend.knowledge.test_ingest_document` | 2 | 通过 |
| `backend.knowledge.test_ingest_pipeline` | 10 | 通过 |
| `backend.knowledge.test_pdf_loader` | 4 | 通过 |
| `backend.knowledge.test_embedding` | 8 | 通过（含真实模型，首次耗时 33.7s，其中约 28s 为模型下载） |
| **合计** | **87** | **全部通过**（模型缓存后全量 `discover` 仅 2.15s） |

可复现命令（从仓库根执行）：

```bash
.venv\Scripts\python.exe -B -m unittest discover -s backend -t .
```

**无网络且模型未缓存时会失败**：沙箱无网络时 `discover` 的结果是 `Ran 87 tests ... FAILED (errors=1)`，唯一错误来自
`ChineseSemanticSimilarityTests.test_similar_sentences_are_closer_than_unrelated_sentences`：
`ValueError: Could not load model BAAI/bge-small-zh-v1.5 from any source.`，被包装为 `EmbeddingError: Unable to load embedding model`。下载模型后即转为通过。

### 6.2 后端接口实测（uvicorn 真实启动）

以占位密钥 `DEEPSEEK_API_KEY=dummy-startup-check-only` 启动 `uvicorn backend.main:app --host 127.0.0.1 --port 8000`：

| # | 操作 | 实测结果 | 判定 |
| --- | --- | --- | --- |
| 1 | 启动 | `Application startup complete.` / `Uvicorn running on http://127.0.0.1:8000`，就绪约 3.5 秒 | 通过 |
| 2 | `GET /api/hello` | `200` + `{"message":"Hello, DMU AI!"}` | 通过 |
| 3 | `POST /api/chat`（仅含 `ai` 消息） | `400` + `{"detail":"请求中没有 user 消息"}` | 通过 |
| 4 | `POST /api/chat`（空 body `{}`） | `422` + Pydantic 校验详情（`missing` / `loc:["body","messages"]`） | 通过 |
| 5 | `OPTIONS /api/chat`（`Origin: http://localhost:5173`） | `200` + `access-control-allow-origin: http://localhost:5173` + `allow-credentials: true` | 通过 |
| 6 | `OPTIONS /api/chat`（`Origin: http://127.0.0.1:5174`） | `400 Bad Request`，响应中**无** `access-control-allow-origin` | 通过（证实端口耦合） |
| 7 | 启动后检查 `data/chroma` | **未创建** | 通过（证实检索器懒加载） |

注意第 3 条：该分支在**检索与 DeepSeek 之前**就返回 400，因此整个接口验证过程没有触发模型加载、没有向量库写入、没有真实 API 调用。**`/api/chat` 成功路径（含 SSE 流式）未验证**，因为它必然调用真实 DeepSeek。

### 6.3 知识检索链路实测（真实模型）

| 步骤 | 命令 | 实测结果 |
| --- | --- | --- |
| 模型可用性 | `-m unittest -v backend.knowledge.test_embedding` | 8/8 通过；首次下载 5 个文件，约 28 秒 |
| 入库 | `-m backend.knowledge.ingest_document "<2026竞赛列表>.pdf" --year 2026 --major 软件工程 --document-type 竞赛列表` | `Chunks imported: 9`，写入 `data/chroma`，collection `knowledge_chunks` |
| 检索评估 | `-m backend.knowledge.evaluate_retrieval --query-id q1` | `Collection size: 9`；top_k=3/5/10 分别返回 3/5/9 条；最高相似度 **0.6837**（其后 0.6507、0.6493…）；人工标注的 4 个竞赛名在三个 top_k 下**全部命中（4/4）** |

说明：仅入库 1 个文档（q1 所针对的竞赛列表），"4/4 命中"只证明**检索链路可用且在该文档内定位准确**，不代表 10 份文档全量入库后的检索质量。

### 6.4 本轮新发现的问题（实测暴露）

1. **`ingest_document.py` 控制台中文乱码**：输出文件名与元数据在 GBK 控制台下显示为 `����1....pdf`。`evaluate_retrieval.py:177-178` 做了 `sys.stdout.reconfigure(encoding="utf-8")`，而 `ingest_document.py` 没有。写入 Chroma 的数据本身正确，仅显示受影响。
2. **embedding 模型缓存落在 `%TEMP%`**：实测缓存目录为 `C:\Users\zyhh2\AppData\Local\Temp\fastembed_cache`，属系统临时目录，可能被清理工具删除，届时需重新下载。可用 `EMBEDDING_CACHE_DIR` 覆盖（`embedding.py:22`）。
3. **Windows 无符号链接权限**：`huggingface_hub` 警告无法创建 symlink（需开发者模式或管理员），缓存以"降级模式"存储、占用更多磁盘；不影响功能。
4. **HF 未认证限流警告**：`You are sending unauthenticated requests to the HF Hub`，未配置 `HF_TOKEN` 时下载速率受限。
5. **`test_retrieval_real.py` 的双重行为**：直接以脚本运行会 `ImportError: attempted relative import with no known parent package`（第 8 行相对导入）；作为包模块导入则正常，且不含任何 test 函数（实测 `has test funcs: []`），因此不产生用例、也不触发 `main()`。文件名具误导性。
6. **`-B` 未完全阻止字节码缓存**：`backend/__pycache__` 与 `backend/knowledge/__pycache__` 仍被创建（被 `.gitignore:3` 覆盖，不影响 git 状态）。

---

## 7. 前端实测结果（构建 + 真实浏览器）

### 7.1 构建与类型检查

| 步骤 | 命令 | 实测结果 |
| --- | --- | --- |
| 依赖安装 | `npm ci` | `added 166 packages in 14s`；`package-lock.json` 零改动 |
| 类型检查 | `npx tsc --noEmit` | **EXITCODE=0，零类型错误**（`strict` / `noUnusedLocals` / `noUnusedParameters` 全开） |
| 生产构建 | `npm run build` | vite v6.4.3，`✓ 281 modules transformed`，`✓ built in 941ms` |
| 构建产物 | —— | `dist/index.html` 419 B、`index.css` 2.61 kB、`index.js` 356.16 kB（gzip 110.34 kB） |

### 7.2 浏览器检查汇总

真实浏览器（Playwright 1.62.1 + 系统 Edge，headless）执行 5 轮、累计 30 余项断言，最终结论：

| 类别 | 结果 |
| --- | --- |
| 界面结构（标题 / 侧栏按钮 / 占位符 / 发送按钮 / 初始空态） | 5 项通过 |
| 交互与渲染（FE-01、02、03、05、06、07、09、10、11、13、14） | 11 项通过 |
| FE-08 中止残留空气泡 | **发现缺陷（已复现，见第 3 节）** |
| FE-12 自动滚底 | 通过；附 25px 余量瑕疵 |
| FE-04 中文输入法 | **未验证**（headless 无法触发组字） |

### 7.3 测试过程中的自我修正（重要：避免误报）

本轮测试前后修正了 6 处**我自己的测试缺陷**，其中两处若直接上报就会变成误报，特此记录：

1. 第 1 轮的 FE-12 被判"通过"，但实际内容是 `top:0, height:540, client:540`——**根本没有溢出**，属无条件通过的假阳性。已重做并在 7.4 给出结论。
2. 第 2 轮 FE-12 被判"失败"（`gap=25px`）→ 第 3、4 轮精确测量显示：最新消息底部在可视区内 10px、复制按钮在内 22px，**内容完全可见**，25px 只是容器内边距余量。**若照第 2 轮上报即为误报。**
3. 第 2 轮 FE-08b"首块到达前中止"**实际从未发生**：前一流仍在进行，`loading` 守卫把发送拦掉了；从请求体长度反推才发现问题。第 5 轮改为"等流结束→发送→250ms 内中止"才真正复现。
4. 第 2 轮 FE-06 判"失败"（4 个请求）→ 实为测试设计错误：生成中点击按钮的本意就是"停止生成"，中止后自然可以再发。第 4 轮改为"生成中连按 Enter"后确认守卫有效。
5. 第 2 轮 FE-14 判"失败"（480 vs 440）→ 实为断言算法错误：`.chat-box` 为 content-box，480 = 440 内容 + 上下内边距 40。第 3 轮用 computed 与 bounding 双值确认通过。
6. 第 2 轮"控制台存在错误"→ 逐条定位为 `GET /favicon.ico → 404` 与测试自身故意 abort 的请求，**非应用缺陷**。

### 7.4 前端侧的新发现

1. **未声明 favicon**：浏览器请求 `/favicon.ico` 返回 **404**，控制台留下一条 404 记录。无功能影响，但 `index.html` 缺少 favicon 声明（`frontend/index.html:6-7` 之间）。
2. **自动滚底余量 25px 不收敛**：流结束后等待 2 秒，`gap` 仍为 25px。推断为 `scrollTo` 的目标 `scrollHeight` 取自 effect 执行时刻、而内容随后又长高 25px，且 `behavior:"smooth"` 在无新消息时不再触发动画。功能影响轻微（内容仍可见），但属可改进点。
3. **中止后输入框不清空**：`App.tsx:153-159` 的提前 `return` 跳过了 `setQuestion("")`（152 行），因此输入框保留原文。这既是"停止后可重发"的前提，也是 FE-08 缺陷的成因之一。
4. **npm 11 拦截了 esbuild 的 postinstall**（`install-scripts ... allowScripts` 警告），实测**不影响** vite 构建与 dev server。

### 7.5 前端仍未验证的部分

- **FE-04 中文输入法组字**：需人工在真实输入法下确认。
- **SSE `error` 事件路径**：真实链路只跑通了成功路径。

### 7.6 真实链路端到端验证（真实 DeepSeek）

使用真实 `DEEPSEEK_API_KEY` 启动 `uvicorn backend.main:app`（端口 8000）+ 真实 vite dev server（5173），由 Playwright 驱动系统 Edge 走完整链路。**不会再出现 mock**。

| # | 项目 | 实测结果 |
| --- | --- | --- |
| 1 | 直接 POST 真实 RAG 问题 | HTTP 200；**535 个 content 事件 / 0 个 error / 1 个 `[DONE]`**；原始 SSE 格式逐字符合契约 |
| 2 | 回答质量与 RAG 生效 | 回答中出现"**依据**：**资料3**中列有…"，明确引用知识库资料编号，证明检索内容进入了 prompt 并影响输出 |
| 3 | RAG 约束性（反向验证） | 提问"奖学金评定依据"时，模型回答"知识库资料仅列出本科生创新创业竞赛信息，未包含奖学金评定办法，因此无法据此说明…"——**未编造**，说明 RAG 提示约束有效 |
| 4 | 前端真实流式 | 聊天区字符数 37 → 92 递增；"AI正在思考..."提示可见；回答正常渲染 |
| 5 | 真实回答复制 | 点击复制后按钮变"已复制"，**剪贴板内容与消息内容完全一致**（`"收到" === "收到"`） |
| 6 | 真实链路下 FE-08 | 首块到达前中止 → 下一次请求体实测为 `["user:27","ai:59","user:9","ai:0","user:8"]`，**`ai:0` 确实送达真实后端** |
| 7 | **空 assistant 消息的上游后果** | **真实 DeepSeek 不拒绝**：该请求返回 HTTP 200 并正常回答（"收到。"），0 个 error 事件。直接构造 `[user, ai(""), user]` 请求同样返回 200 |
| 8 | 后端日志 | 全程无 Traceback、无 500、无 Exception |
| 9 | 浏览器控制台 | 除 favicon 404 外无错误 |

**结论**：FE-08 的**上游后果为良性**——空 `assistant` 消息会污染会话历史并多消耗少量 token，但**不会导致请求失败**。原审查报告中"是否被模型拒绝 → 待确认"这一问题现已明确：**否**。

**测试过程自我修正（本轮新增 2 处）**：

1. 剪贴板首次判"失败"（读到 11 字符）——实为脚本**漏写 `grantPermissions`**，读到的 11 字符正好是 `"READ_FAILED"` 错误哨兵值。
2. 第二次判"失败"（回答 9 vs 剪贴板 5）——实为断言方法错误：`.message.ai` 气泡内部**包含复制按钮**，`innerText` 会带上"复制"两字（实测 `"收到\n\n复制"` 共 6 字符）。剔除按钮后确认完全一致。

---

## 8. 风险确认项（需负责人先决策才能执行）

---

## 8. 风险确认项（需负责人先决策才能执行）

| 编号 | 事项 | 为什么必须先确认 | 结果 |
| --- | --- | --- | --- |
| RISK-01 | 是否允许真实调用 DeepSeek API | 已获授权并执行：真实链路端到端跑通（见 7.6），消耗少量额度 | **已完成** |
| RISK-02 | 是否允许联网下载 embedding 模型 | 已执行：下载成功（5 个文件、约 28 秒），`test_embedding` 由失败转通过 | **已完成** |
| RISK-03 | 是否允许写入 `data/chroma` 向量库 | 已执行：入库 1 个文档（9 chunks）。目录被 `.gitignore:8` 覆盖 | **已完成（1/10 文档）** |
| RISK-04 | 是否允许安装依赖 | 后端已用仓库内 `.venv`；前端已用 `%TEMP%` 下的 Node.js 官方 ZIP + `npm ci`，**系统级 Node 安装与 `npm install` 均未执行**。若需长期开发，仍建议正装 Node.js | **临时方案已完成 / 系统级安装待确认** |
| RISK-05 | 客户端能否注入 `role:"system"` | **已实测证实**：传入 `role="system"` 的消息后，`_build_deepseek_messages` 会原样转发，产出第二个 system 条目，与受控 system 并列 | **已证实，待决定是否按漏洞修复** |

---

## 9. 执行记录

| 日期 | 执行人 | 命令 / 操作 | 结果摘要 |
| --- | --- | --- | --- |
| 2026-10-16 | 代码审查 | `npm run` / `npm run build` / `npm run lint` / `npm run test` | 4 条全部失败：`'npm' is not recognized...`，EXITCODE=1（npm 不存在，脚本内容从未被读取） |
| 2026-10-16 | 代码审查 | `python -B -c "import fastapi, chromadb, fastembed, pypdf, openai, pytest"` | 8 项依赖全部 MISSING |
| 2026-10-16 | 代码审查 | 只读检查（git / 目录 / 源码通读 / 关键词检索 / Test-Path） | 无副作用；工作区变更文件数 0 |
| 2026-10-16 | 复测 | `python -m venv .venv` + `pip install -r backend\requirements.txt` | 成功安装 7 项声明依赖（未新增包） |
| 2026-10-16 | 复测 | `-m unittest` 逐模块运行 11 个 mock 模块 | **79/79 通过** |
| 2026-10-16 | 复测 | `-m unittest discover -s backend -t .`（模型未缓存 / 沙箱无网络） | `Ran 87 tests` → **FAILED (errors=1)**，1 个错误为模型无法加载 |
| 2026-10-16 | 复测 | `-m unittest -v backend.knowledge.test_embedding`（联网下载模型） | 8/8 通过，耗时 33.7s（含 28s 下载） |
| 2026-10-16 | 复测 | 再次 `-m unittest discover -s backend -t .` | `Ran 87 tests in 2.150s` → **OK** |
| 2026-10-16 | 复测 | `uvicorn backend.main:app` + 6 项接口 / CORS 请求 | 全部符合预期（见 6.2）；进程已停止；`data/` 未被启动过程创建 |
| 2026-10-16 | 复测 | `-m backend.knowledge.ingest_document`（入库 1 个 PDF） | `Chunks imported: 9` |
| 2026-10-16 | 复测 | `-m backend.knowledge.evaluate_retrieval --query-id q1` | 4/4 命中，最高分 0.6837 |
| 2026-10-16 | 复测 | `npm run` / `build` / `lint` / `test` | **4 条仍全部失败**（npm 不存在），前端无法验证 |
| 2026-10-16 | 复测 | 下载 Node.js 官方 ZIP 至 `%TEMP%`（v24.22.0 LTS + npm 11.19.1） | 成功；未做系统级安装、不写注册表 |
| 2026-10-16 | 复测 | `npm ci`（frontend） | `added 166 packages in 14s`；`package-lock.json` 零改动 |
| 2026-10-16 | 复测 | `npx tsc --noEmit` | **EXITCODE=0，零类型错误** |
| 2026-10-16 | 复测 | `npm run build` | 成功；281 模块，941ms，产出 `dist/` |
| 2026-10-16 | 复测 | `npm run dev`（vite 5173） | 启动成功；`GET /` 返回 **200** |
| 2026-10-16 | 复测 | 启动本地 mock（与真实 SSE 契约一致，端口 8000） | `GET /api/hello` 200；SSE 输出与 `backend/main.py` 一致 |
| 2026-10-16 | 复测 | Playwright + 系统 Edge 第 1 轮（22 项） | 20 通过 / 2 失败；经复核 2 项均为测试自身问题 |
| 2026-10-16 | 复测 | 第 2 轮（22 项，加大 mock 延迟与内容量） | 19 通过 / 3 失败；3 项中 2 项为测试问题、1 项需精确定量 |
| 2026-10-16 | 复测 | 第 3 轮（5 项精确测量） | 确认 FE-14 通过、404 为 favicon；FE-12 余量 25px 稳定不收敛 |
| 2026-10-16 | 复测 | 第 4 轮（4 项） | FE-06 守卫有效；FE-12 的最新消息与复制按钮**完整可见**（修正误报） |
| 2026-10-16 | 复测 | 第 5 轮（6 项，正确复现首块前中止） | **复现 FE-08 缺陷**：请求体出现 `ai:0` |
| 2026-10-16 | 复测 | 清理：停止 vite / mock 进程并复查端口 | 5173 / 8000 / 8011 均已释放，无我方进程残留 |
| 2026-10-16 | 复测 | 真实后端 + 真实 DeepSeek：直接 POST RAG 问题 | HTTP 200；535 content / 0 error / 1 `[DONE]`；回答引用「资料1/资料3」 |
| 2026-10-16 | 复测 | 真实后端：构造含空 `ai` 消息的历史（模拟 FE-08） | HTTP 200 正常回答 —— **上游不拒绝空 assistant 消息** |
| 2026-10-16 | 复测 | 真实链路浏览器验证（vite 5173 + 后端 8000） | 9/10 通过；唯一失败为脚本漏 `grantPermissions` |
| 2026-10-16 | 复测 | 剪贴板复测（剔除气泡内的复制按钮文字） | 3/3 通过；`剪贴板 === 消息内容` |
| 2026-10-16 | 复测 | 清理：停止真实后端与 dev server | 5173 / 8000 已释放；确认 API key **未写入仓库任何文件** |

**当前状态：后端 87/87 通过；前端构建 + 浏览器检查通过；真实 DeepSeek 端到端链路跑通。FE-08 缺陷已复现且上游后果为良性；FE-04 中文输入法需人工确认。**

