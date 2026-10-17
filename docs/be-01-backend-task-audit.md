# BE-01：后端任务 API、数据模型与持久化只读审查

| 项目 | 内容 |
| --- | --- |
| 仓库 | `kento-wts/DMU-AI-Learning-Assistant` |
| 审查对象 | `backend/tasks/**`、`backend/main.py` 的任务接口注册、任务持久化与测试 |
| 审查分支 | `feat/task-api` |
| 被审提交 | `ee2f546` |
| 审查日期 | 2026-10-17 |
| 审查方式 | 只读核对工作区代码、Git 对象、路由注册、持久化实现与测试执行 |
| 证据分级 | 已实现（有代码与行为证据）/ 部分实现 / 尚未实现 / 需运行测试确认 |

> 本轮只做审查：未修改代码、未安装依赖、未更新锁文件、未修改数据库、未提交、未创建 PR。
> 未执行 `fetch`，远程状态使用只读 `git ls-remote` 核对。

---

## 0. 审查范围与前提

### 0.1 必须是先说明的两点

1. `main` 分支（`379b6e8`）上不存在任何任务代码。`git ls-tree -r --name-only main -- backend/tasks` 返回空。任务模块仅存在于 `feat/task-api`。
2. 远程已有本地未拉取的新提交：

| 远程分支 | 远程提交 | 本地是否存在该对象 |
| --- | --- | --- |
| `main` | `379b6e8` | 是 |
| `feat/task-api` | `ee2f546` | 是（本人分支） |
| `feat/agent` | `379b6e8` | 是（尚未开发） |
| `feat/rag-verification` | `8928204` | 否（未 fetch） |
| `feat/task-ui-zyhh` | `11d99fc` | 否（未 fetch） |

因此前端分支与 RAG 分支的最新内容本轮无法离线审阅，标注为「待确认」。

### 0.2 工作区状态

| 项目 | 值 |
| --- | --- |
| 当前分支 | `feat/task-api` |
| HEAD | `ee2f546`（2026-10-16 20:15，zbj） |
| 工作区 | 干净（`git status --porcelain` 为空） |

### 0.3 磁盘现状

```
data/                -> 不存在
data/tasks.json      -> 不存在
data/chroma/         -> 不存在
backend/.env         -> 不存在
backend/.venv        -> 存在（已安装依赖）
```

---

## A. 当前后端架构与模块调用关系

### A.1 实际目录结构（`backend/`，排除 `.venv` 与 `__pycache__`）

```
backend/
├── main.py                    ASGI 入口 + 聊天接口
├── rag_chat.py                 非流式 RAG 服务（无生产调用，仅测试引用）
├── requirements.txt
├── test_main.py / test_rag_chat.py
├── knowledge/                  RAG（他人负责，本轮不审）
│   └── ... + documents/（10 份 PDF）
└── tasks/                      任务模块（本次审查对象）
    ├── __init__.py             模块入口，仅导出领域层
    ├── store.py                领域层 + 数据访问（纯标准库）
    ├── models.py               Pydantic 请求/响应模型
    ├── router.py               APIRouter（5 个端点）
    ├── test_task_store.py      51 个测试
    └── test_task_router.py     37 个测试
```

### A.2 路由注册与调用链（有代码证据）

```
uvicorn backend.main:app
└── backend/main.py:37   app = FastAPI(...)
    ├── backend/main.py:40  CORS 中间件
    ├── backend/main.py:51  app.include_router(tasks_router)   ← 唯一注册点
    │    ▲ import 来源：backend/main.py:15
    │    └── backend/tasks/router.py:27  APIRouter(prefix="/api/tasks")
    │         ├── router.py:48  TaskStoreDep = Annotated[TaskStore, Depends(get_task_store)]
    │         └── router.py:33-45  get_task_store()（进程内单例，双重检查锁）
    │              └── backend/tasks/store.py:79  class TaskStore
    │                   ├── store.py:90   内存 dict[str, Task]
    │                   ├── store.py:212  _load()  ← 启动时读
    │                   └── store.py:242  _save()  ← 每次写
    │                        └── <仓库根>/data/tasks.json（store.py:44）
    ├── backend/main.py:132  @app.get("/api/hello")
    └── backend/main.py:137  @app.post("/api/chat")   ← 未改动
         └── main.py:146 _get_retriever() → knowledge/Retriever → ChromaVectorStore
```

### A.3 分层评估

| 层 | 现状 | 结论 |
| --- | --- | --- |
| 路由层 | `router.py` 很薄：只做 Pydantic 入参、异常到 HTTP 的映射、调用 store | 分离良好 |
| 业务逻辑层 | 与数据访问合并在 `TaskStore` 内（校验规则 + CRUD + 文件读写） | 部分分离：两层合并 |
| 数据访问层 | `_load` / `_save`（`store.py:212-253`）为私有方法，无独立仓储接口 | 无独立抽象 |

真实存在的耦合问题：

1. 持久化生命周期归路由层所有：`get_task_store()`（`router.py:33-45`）本属数据访问关注点，却写在 HTTP 层。
2. 校验逻辑重复且已产生分歧：`models.py:112-129 _normalise_due_date` 与 `store.py:293-311 _validate_due_date` 是两份实现，行为不同（见 E-P1-2）。
3. `main.py` 的聊天业务逻辑仍内联在路由函数中（`main.py:137-193`）。属他人范围，本轮只记录不处理。

---

## B. API 清单

> 判定规则：只有 `feat/task-api` 上有任务接口；`main` 上只有前两条。

| # | 方法 | 路径 | 用途 | 请求 | 响应 | 实现位置 | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `GET` | `/api/hello` | 健康检查 | 无 | `{"message": "Hello, DMU AI!"}` | `main.py:132` | 已实现（两个分支均有） |
| 2 | `POST` | `/api/chat` | 多轮聊天 + RAG + SSE | `ChatRequest` | `text/event-stream` | `main.py:137` | 已实现，本次未改动 |
| 3 | `POST` | `/api/tasks` | 创建任务 | `CreateTaskRequest` | `TaskResponse` / `201` | `router.py:59` | 已实现（仅 feat/task-api） |
| 4 | `GET` | `/api/tasks` | 列表（可过滤/分页） | query: `status`、`limit`(1-200)、`offset` | `TaskListResponse` / `200` | `router.py:80` | 已实现 |
| 5 | `GET` | `/api/tasks/{task_id}` | 单条查询 | 路径参数 | `TaskResponse` / `200` | `router.py:106` | 已实现 |
| 6 | `PATCH` | `/api/tasks/{task_id}` | 局部更新（含状态） | `UpdateTaskRequest` | `TaskResponse` / `200` | `router.py:122` | 已实现 |
| 7 | `DELETE` | `/api/tasks/{task_id}` | 删除 | 路径参数 | `204` 无响应体 | `router.py:146` | 已实现（超出原需求，需确认是否保留） |

错误响应统一格式为 `{"detail": "..."}`：`404` 任务不存在，`422` 字段校验失败，`400` 业务规则冲突。

---

## C. 数据模型清单

### C.1 业务实体 `Task`（`store.py:62`，`@dataclass(frozen=True)`）

| 字段 | 类型 | 约束 | 证据 |
| --- | --- | --- | --- |
| `id` | `str` | 服务端生成 `uuid4().hex`（32 位小写十六进制），不可修改 | `store.py:139`、`store.py:46` |
| `title` | `str` | 必填；去首尾空格后非空；最长 200 字符 | `store.py:40,267-277`；`models.py:29` |
| `description` | `str` | 可选，默认空串；去首尾空格；最长 2000 字符 | `store.py:41,280-290` |
| `due_date` | `str` 或 `null` | 可选；严格 `YYYY-MM-DD`；非法日期拒绝 | `store.py:293-311` |
| `status` | `str` | `pending` / `in_progress` / `done`，默认 `pending` | `store.py:19-26,37` |
| `source` | `str` | `manual` / `chat` / `agent`，默认 `manual` | `store.py:28-38` |
| `created_at` | `str` | 服务端生成，UTC ISO 8601（带微秒） | `store.py:262-264` |
| `updated_at` | `str` | 每次 update 刷新；创建时等于 `created_at` | `store.py:187` |

关联关系：无。没有 `owner`、`assignee`、`conversation_id`、`source_document` 等外键或引用字段。

### C.2 Pydantic 模型（`models.py`）

| 模型 | 位置 | 说明 |
| --- | --- | --- |
| `CreateTaskRequest` | L24-50 | `extra="forbid"`；`title` 必填、`description` 默认空、`status`/`source` 有默认值；自定义 strip 与空标题校验 |
| `UpdateTaskRequest` | L53-83 | 全部字段可空；配合 `model_dump(exclude_unset=True)` 实现局部更新 |
| `TaskResponse` | L86-100 | 8 个字段；`from_task()` 由 `Task.to_dict()` 构造 |
| `TaskListResponse` | L103-109 | 对象信封：`items` / `total` / `limit` / `offset` |
| `TaskStatus` / `TaskSource` | L18-19 | `Literal`，与 `store.py` 常量由 2 个一致性测试锁死 |

聊天仅有两个请求模型（`Message` `main.py:77`、`ChatRequest` `main.py:82`），没有任何响应模型。

---

## D. 持久化现状

| 数据 | 存储方式 | 生命周期 | 重启后是否保留 | 证据 |
| --- | --- | --- | --- | --- |
| 任务 | 单文件 JSON：`<仓库根>/data/tasks.json` | 进程启动时 `_load()` 读入内存；每次写操作全量重写 | 是（内存从文件重建） | `store.py:44,212-240,242-253` |
| 聊天会话 | 无持久化（在前端 `messages` 状态里） | 页面刷新即丢 | 否 | `frontend/src/App.tsx:14` |
| RAG 向量 | Chroma `PersistentClient` → `data/chroma/` | 进程外持久化 | 是（属他人范围） | `knowledge/chroma_store.py:50` |
| 数据库 | 不存在 | — | — | 全后端检索 `sqlite`/`sqlalchemy`/`psycopg`/`pymongo`/`redis` 零命中 |
| 外部服务 | 不存在 | — | — | 同上 |

### D.1 写入一致性设计（已实现）

- 原子替换：先写 `tasks.json.tmp`，再 `os.replace()`（`store.py:246-251`），崩溃不会产生半截文件
- 失败回滚：`create`/`update`/`delete` 在写盘异常时恢复内存（`store.py:151-155,189-193,206-210`）
- 并发保护：`threading.RLock`（`store.py:89`）

### D.2 明确的能力边界

| 能力 | 状态 |
| --- | --- |
| 单进程内存并发安全 | 已实现 |
| 跨进程 / 多 worker 安全 | 尚未实现（无文件锁，`uvicorn --workers N` 会互相覆盖） |
| 数据在团队成员间共享 | 尚未实现（文件在本地且被 `.gitignore` 排除） |
| 重启后保留（单元测试层） | 已实现且有测试（`test_tasks_survive_reload` 等 4 个） |
| 重启后保留（真实 HTTP 端到端） | 未验证 |

任务模块虽然实现了持久化，但从未在该工作区真实落盘过——所有测试都使用 `tempfile.TemporaryDirectory()`。因此「重启后数据还在」目前只有单元测试证据，没有端到端证据。

---

## E. 问题清单

> 分级标准：P0 = 阻塞目标流程；P1 = 影响正确性/安全，但不阻塞主流程；P2 = 工程质量改进。

### P0

#### P0-1 任务模块尚未进入 `main`，Agent 与前端无法在主干上对接

- 证据：`git ls-tree -r --name-only main -- backend/tasks` 返回空；`main` = `379b6e8`；`feat/task-api` 领先 3 个提交
- 影响：主负责人基于 `main` 开发 Agent 时看不到任何任务接口，存在重复实现风险
- 建议：先合入 `main`，或让 Agent 从 `feat/task-api` 拉分支

#### P0-2 不支持批量、原子写入，无法安全落地 Agent 的「任务计划」

- 证据：`router.py` 仅有单条 `POST /api/tasks`（L59）；`store.create`（`store.py:122`）一次一条
- 影响：一个计划含 N 条任务时只能循环调用；第 k 条失败会留下半个计划，且无回滚
- 建议：见 G 节

### P1

#### P1-1 `PATCH` 传 `null` 返回 400 而非 422（已实测）

- 证据：`PATCH {"title": null}` 返回 `400 {"detail":"title must be a string"}`；而 `PATCH {"title": 123}` 返回 `422`
- 根因：`models.py:62-66` 字段声明为可空（放行 `null`）→ `router.py:132` 原样下传 → `store.py:268` 抛 `TypeError` → `router.py:140` 映射为 400
- 影响：前端表单把清空字段绑成 `null` 会得到内部错误式的 400，而非带字段定位的 422
- 建议：在 `UpdateTaskRequest` 的校验器里显式拒绝 `null`（`due_date` 除外）

#### P1-2 `due_date` 空串语义两层相反（已实测）

- 证据：`PATCH {"due_date": ""}` 返回 `200` 并静默清空；`store.update(due_date="")` 抛 `ValueError: due_date must not be blank`
- 根因：`models.py:117-119`（空串转 `None`）与 `store.py:299-301`（空串报错）两份实现
- 建议：二选一并统一，同时补测试固化

#### P1-3 `TaskStorageError` 未映射到 HTTP

- 证据：`router.py` 只映射 `TaskNotFoundError` / `TypeError` / `ValueError`（L51-56 及 5 个端点）
- 影响：`data/tasks.json` 损坏时返回 500，且 `_store` 保持 `None`，每个请求重复失败
- 状态：推断，未实测
- 建议：映射为 `503` 并给出可诊断的 detail

#### P1-4 多进程不安全

- 证据：`store.py:89` 仅 `threading.RLock`；`router.py:40-45` 单例为进程级
- 影响：`uvicorn --workers N` 时各 worker 各持一份内存副本，全量重写导致后写覆盖先写
- 建议：部署文档明确单 worker；或改用 SQLite（可只改 `store.py`）

#### P1-5 无幂等，重试会产生重复任务

- 证据：`store.py:139` 每次 `uuid4().hex`，无客户端去重键
- 影响：前端重试、网络超时重发、Agent 重跑都会产生重复任务
- 建议：后续引入幂等键（如 `source` 与 `client_request_id` 组合）

#### P1-6 无鉴权与授权

- 证据：全后端无任何认证依赖；`router.py` 5 个端点均无安全校验
- 影响：任何能访问 8000 端口者都可读写删除全部任务；也无任务归属
- 说明：当前 CORS 仅放行 `localhost:5173`（`main.py:42-45`），但 CORS 不是认证
- 建议：本地演示可接受；一旦对校园网开放即为 P0

#### P1-7 存储路径不可配置

- 证据：`router.py:43` 直接 `TaskStore()`，恒用 `store.py:44` 的 `DEFAULT_STORE_PATH`
- 影响：部署无法改路径；测试只能靠 `dependency_overrides` 绕开

#### P1-8 后端当前无法启动（配置缺失）

- 证据：`main.py:22-27` 在缺少 `DEEPSEEK_API_KEY` 时 `raise RuntimeError`；`backend/.env` 不存在
- 影响：任何端到端验证（含任务接口）都会被 `import backend.main` 阻断
- 说明：这是配置问题而非代码缺陷；按要求未创建 `.env`

### P2

| # | 问题 | 证据 | 建议 |
| --- | --- | --- | --- |
| P2-1 | 日期校验重复实现（DRY） | `models.py:112-129` 与 `store.py:293-311` | 抽到单一位置 |
| P2-2 | 分页/排序在内存完成 | `router.py:96`、`store.py:119` | 数据量大时下推 |
| P2-3 | 全量重写文件 | `store.py:242-251` | O(n)，可接受 |
| P2-4 | 无优先级/排序字段 | `store.py:62-72` | 视产品需要 |
| P2-5 | `httpx` 未列入依赖，测试难复现 | `requirements.txt` 无 httpx；`TestClient` 需要它 | 增加 dev 依赖文件 |
| P2-6 | README 未记录任务 API | `README.md` | 补文档 |
| P2-7 | `DELETE` 超出原需求 | `router.py:146` | 需负责人确认保留 |

---

## F. 测试现状

### F.1 本轮实际执行的命令与结果（含退出码）

| # | 命令 | 实际输出 | 退出码 |
| --- | --- | --- | --- |
| 1 | `python -B -m unittest backend.tasks.test_task_store` | `Ran 51 tests` — `OK` | 0 |
| 2 | `.venv\Scripts\python.exe -B -m unittest backend.tasks.test_task_router` | `Ran 37 tests` — `OK` | 0 |
| 3 | `.venv\Scripts\python.exe -B -m unittest backend.tasks.test_task_store backend.tasks.test_task_router` | `Ran 88 tests` — `OK` | 0 |
| 4 | `.venv\Scripts\python.exe -B -m unittest backend.test_main` | `Ran 7 tests` — `OK` | 0 |
| 5 | `.venv\Scripts\python.exe -B -m unittest backend.test_rag_chat` | `Ran 11 tests` — `OK` | 0 |

副作用检查：运行前后 `data/` 均为 `False`；`git status` 全程为空，测试未产生任何文件改动。

### F.2 覆盖率（本轮实测，自制 `sys.settrace` 探针）

| 文件 | 语句覆盖 | 未执行行 |
| --- | --- | --- |
| `store.py` | 200/215（93%） | `154,155,174,180,192,193,209,210,220,253,264,327,347,352,359` |
| `models.py` | 66/67（98%） | `119` |
| `router.py` | 46/57（80%） | `38,40,41,42,43,45,75,94,117,141,158` |

### F.3 已覆盖功能

创建（默认值/全字段/唯一 ID/去空格）、标题与描述边界、状态与来源取值、`due_date` 格式、`get`/`list`/过滤/排序、`update`（标题/状态/清空 due_date）、未知字段、空更新、`delete`、重启重载、文件损坏（JSON 非法/非数组/缺字段/非法状态）、不可变性、HTTP 层 201/200/204/400/404/422、分页与 limit 边界、响应字段完整性。

### F.4 缺少的关键路径

1. `update()` 修改 `description`、`source`（`store.py:174,180` 未执行）
2. 默认时钟 `_utc_now_iso()` 从未执行（`store.py:264`），生产时间戳格式未验证
3. `get_task_store()` 生产分支从未执行（`router.py:38-45`），所有测试都使用 `dependency_overrides`
4. `PATCH` 传 `null` 的 400 分支（`router.py:141`），即 P1-1 的路径无测试
5. `TaskStorageError` 到 HTTP 的映射（尚未实现，故无测试）
6. 写盘失败回滚（`store.py:154-155,192-193,209-210`）
7. 记录非 dict、时间戳为空/格式非法（`store.py:359,347,352`）
8. `_validate_source` 的 `TypeError`（`store.py:327`）

### F.5 未验证项

| 项目 | 状态 |
| --- | --- |
| 真实 `uvicorn` 启动（被 P1-8 阻断） | 未执行 |
| HTTP 层「重启后数据还在」端到端 | 未验证 |
| 多进程并发写 | 未验证 |
| `TaskStorageError` 的实际 HTTP 码 | 未实测（推断 500） |
| `feat/task-ui-zyhh` / `feat/rag-verification` 最新代码 | 本地无对象，待确认 |

---

## G. 下一阶段建议：只推荐一个最小任务

### BE-02：原子批量创建任务

#### 任务目标

新增一个原子批量创建接口，使「Agent 生成任务计划 → 用户确认 → 一次性保存」具备后端能力：要么全部成功，要么全部不落盘。

#### 修改文件范围（5 个，全部在本模块内）

| 文件 | 改动 |
| --- | --- |
| `backend/tasks/store.py` | 新增 `create_many(items) -> list[Task]`：先全部校验、再一次性写入，失败整体回滚 |
| `backend/tasks/models.py` | 新增 `CreateTasksRequest`（含条数上限） |
| `backend/tasks/router.py` | 新增 `POST /api/tasks/batch` |
| `backend/tasks/test_task_store.py` | 原子性/回滚测试 |
| `backend/tasks/test_task_router.py` | 接口契约测试 |

不改 `main.py`（router 已注册）、不改前端、不改 `knowledge/`、不引入依赖。

#### API 与数据模型契约（提案，待负责人确认）

```http
POST /api/tasks/batch
Content-Type: application/json

{ "tasks": [ { "title": "报名", "due_date": "2026-11-01", "source": "agent" }, { "title": "交材料" } ] }
```

- `201 Created`：`{ "items": [TaskResponse, ...], "total": 2 }`
- `tasks` 条数：1 至 50（上限待确认）
- 空数组 / 超上限 / 任一条字段非法：返回 `422`，store 不产生任何变化
- 写盘失败：返回 `503`，内存与文件均回滚
- 单条结构完全复用现有 `CreateTaskRequest`，不改变已有 5 个端点

#### 错误处理要求

1. 校验必须先于任何写入（先在内存构造完整记录，再落盘）
2. 任一失败不得留下部分记录（内存与文件一致）
3. 错误格式沿用 `{"detail": ...}`

#### 测试用例与验收标准

- [ ] 1 条返回 `201`，落盘 1 条
- [ ] 50 条返回 `201`，全部落盘，`id` 唯一
- [ ] 0 条返回 `422`，store 数量不变
- [ ] 51 条返回 `422`，store 数量不变
- [ ] 第 3 条非法（空标题）返回 `422`，前 2 条也不得写入
- [ ] 写盘失败（monkeypatch `_save`）抛出存储异常，内存回滚到调用前状态
- [ ] 现有 88 个测试仍全部通过；`test_main` / `test_rag_chat` 仍通过
- [ ] `GET /api/tasks` 能正确列出批量创建的结果，且分页总数正确

#### 依赖关系

| 依赖 | 说明 |
| --- | --- |
| 负责人 | 确认条数上限、响应信封、是否要幂等键 |
| 前端（C / feat/task-ui-zyhh） | 确认「确认后一次性提交」的交互，以及错误码处理 |
| Agent（主负责人） | 确认走 HTTP 还是服务端直接调用 `TaskStore.create_many` |
| RAG（A） | 无依赖 |
| 冲突面 | 仅 `backend/tasks/**`；`main.py` 不需要改动 |

---

## H. 最终结论

| 维度 | 状态 | 依据 |
| --- | --- | --- |
| 任务 API | 已实现，但未合入主干 | 5 个端点在 `feat/task-api`；`main` 上零任务代码；88 个测试通过 |
| 数据模型 | 已实现，基本完整 | `Task` 8 字段 + 4 个 Pydantic 模型；缺 `owner`、来源关联、优先级 |
| 持久化 | 部分实现 | 单进程 JSON 原子写已实现；重启保留有单测证据；跨进程/共享/端到端未实现或未验证 |

为什么优先做 BE-02：

1. 现有能力已能接收、保存、管理单条任务，唯一功能性缺口就是「计划」这一粒度；
2. 它是唯一能让端到端流程跑通的最小增量，且不触碰 `/api/chat`；
3. 改动集中在 `backend/tasks/**` 五个文件，可独立验收，不依赖 RAG 或前端改造；
4. 相比先修 P1-1/P1-2（接口行为一致性），批量创建解决的是「有没有能力」，而 P1 解决的是「行为是否一致」；在流程尚未打通前，优先补能力更划算。

建议的后续顺序：BE-02 批量原子创建 → P1-1/P1-2 写入语义统一 → P1-3 存储异常映射 → P1-4/P1-6 部署与安全 → P2 清理。

---

## 本轮执行声明

- 未修改任何代码、未安装依赖、未更新锁文件、未修改数据库、未 commit、未创建 PR
- 未执行 `fetch`，未写入 `.git`；远程状态用只读 `git ls-remote` 核对
- 只运行了现有测试（5 条命令，退出码均为 0），运行前后 `data/` 均不存在、工作区干净
- 未调用任何真实大模型 API；未读取或输出任何密钥（`backend/.env` 本身不存在）
- 标注为「未验证」「待确认」「推断」的内容均未经实际验证，不应视为已通过