# 后端任务管理能力审查报告

## 能否接收、保存和管理 Agent 生成的任务？

| 项目 | 内容 |
| --- | --- |
| 审查问题 | 后端现在有没有能力接收、保存和管理 Agent 生成的任务 |
| 审查对象 | `backend/**` 在 `main` 与 `feat/task-api` 两个分支上的实际状态 |
| 分支对照 | `main` = `379b6e8`；`feat/task-api` = `1189486` |
| 审查方式 | 只读核对 git 对象（`git ls-tree` / `git show` / `git diff`）+ 工作区代码 + 既有测试结果 |
| 日期 | 2026-10-16 |
| 相关文档 | `docs/task-api-code-review.md`（本人第二阶段新代码的逐文件审查与实测覆盖率） |

> 本报告只做审查：不新增接口、不修改任何代码、不新建数据库。

---

## 结论先行

| 分支 | 提交 | 能否接收 / 保存 / 管理 Agent 生成的任务 |
| --- | --- | --- |
| `main` | `379b6e8` | 不能。没有任何任务相关代码 |
| `feat/task-api` | `1189486` | 能（单条）。创建 / 列表 / 单查 / 改状态 / 删除全部具备，且已落盘持久化 |

核对方式：`git ls-tree -r --name-only main -- backend/tasks` 返回空，说明 `main` 上不存在任务模块。该模块仅存在于 `feat/task-api`，领先 `main` 两个提交：

```
defd3cb  feat: add standalone task management module with JSON persistence
1189486  docs: add second-phase code review report for the task module
```

**对团队最关键的一条结论**：如果 Agent 负责人基于 `main` 开发，他将看不到任何任务接口。这是当前最大的协同风险。

---

## 一、现有接口清单

### 1.1 `main` 分支（共 2 个）

| 方法 | 路径 | 请求模型 | 响应 |
| --- | --- | --- | --- |
| `GET` | `/api/hello` | 无 | `{"message": "Hello, DMU AI!"}` |
| `POST` | `/api/chat` | `ChatRequest` | SSE 流式 `text/event-stream` |

### 1.2 `feat/task-api` 分支（`main` 的 2 个 + 新增 5 个）

| 方法 | 路径 | 请求模型 | 响应模型 | 成功码 |
| --- | --- | --- | --- | --- |
| `POST` | `/api/tasks` | `CreateTaskRequest` | `TaskResponse` | `201` |
| `GET` | `/api/tasks` | 查询参数 `status` / `limit` / `offset` | `TaskListResponse` | `200` |
| `GET` | `/api/tasks/{task_id}` | 无 | `TaskResponse` | `200` |
| `PATCH` | `/api/tasks/{task_id}` | `UpdateTaskRequest` | `TaskResponse` | `200` |
| `DELETE` | `/api/tasks/{task_id}` | 无 | 无响应体 | `204` |

路由声明位置：`backend/tasks/router.py`，`APIRouter(prefix="/api/tasks", tags=["tasks"])`。

错误响应统一为 `{"detail": "..."}`：`404` 任务不存在，`422` 字段校验失败，`400` 业务规则冲突。

### 1.3 验证方式

在真实 `backend.main` 应用上读取 OpenAPI 路由表，实测结果：

```
POST              /api/chat              （原有，未变）
GET               /api/hello             （原有，未变）
GET,POST          /api/tasks             （新增）
DELETE,GET,PATCH  /api/tasks/{task_id}   （新增）
```

---

## 二、数据模型说明

### 2.1 `main` 分支：只有 2 个请求模型，没有任何响应模型

```python
class Message(BaseModel):        # main.py:74
    role: str
    content: str

class ChatRequest(BaseModel):    # main.py:79
    messages: list[Message]
```

### 2.2 `feat/task-api` 分支：领域模型 `Task`

定义位置 `backend/tasks/store.py:61`，`@dataclass(frozen=True)`：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `id` | `str` | 服务端生成 `uuid4().hex`，不可修改 |
| `title` | `str` | 必填，去空格后非空，最长 200 字符 |
| `description` | `str` | 可选，默认空串，最长 2000 字符 |
| `due_date` | `str` 或 `null` | 可选，严格 `YYYY-MM-DD` 格式 |
| `status` | `str` | `pending` / `in_progress` / `done`，默认 `pending` |
| `source` | `str` | `manual` / `chat` / `agent`，默认 `manual`（已为 Agent 预留取值） |
| `created_at` | `str` | 服务端生成，UTC ISO 8601 |
| `updated_at` | `str` | 服务端生成，UTC ISO 8601 |

### 2.3 HTTP 模型（`backend/tasks/models.py`）

`CreateTaskRequest`、`UpdateTaskRequest`、`TaskResponse`、`TaskListResponse`，全部设置 `ConfigDict(extra="forbid")`。

状态与来源取值用 `Literal` 声明：`TaskStatus = Literal["pending", "in_progress", "done"]`、`TaskSource = Literal["manual", "chat", "agent"]`。这两个 `Literal` 与 `store.py` 的常量由两个一致性测试锁死。

---

## 三、存储方式与重启后数据是否还在

| 分支 | 存储方式 | 重启后数据是否还在 |
| --- | --- | --- |
| `main` | 唯一持久化是 Chroma 向量库（`data/chroma/`）。聊天历史只在前端内存中，刷新即丢 | 任务相关：不适用 |
| `feat/task-api` | 单文件 JSON：`<仓库根>/data/tasks.json`，首次写入时自动创建，已被 `.gitignore` 忽略 | 在。进程启动时由 `_load()` 读回 |

**写入策略**：先写 `tasks.json.tmp`，再用 `os.replace()` 原子替换，因此进程崩溃不会产生半截文件。写盘失败时会回滚内存改动，保证内存与文件一致。并发由 `threading.RLock` 保护。

**已知限制**：

1. 仅进程内安全，`uvicorn --workers N` 会互相覆盖
2. 每次写入全量重写整个文件，复杂度 O(n)；`list()` 全量载入内存后在路由层切片分页，复杂度 O(n log n)
3. 任务文件只在本地且不进版本库，四名成员各有一份，数据不共享
4. 文件损坏时构造 `TaskStore` 直接抛 `TaskStorageError`，刻意不静默清空数据

**待验证**：「重启后数据还在」目前只由单元测试验证（`test_tasks_survive_reload`、`test_updates_survive_reload`、`test_deletions_survive_reload`、`test_unicode_title_survives_reload`），尚未在真实 uvicorn 服务上端到端验证，也未在生产路径上真实生成过 `data/tasks.json`。

---

## 四、请求与响应格式

### 4.1 创建任务

```http
POST /api/tasks
Content-Type: application/json

{ "title": "准备竞赛报名材料", "description": "需学院盖章", "due_date": "2026-11-01", "source": "agent" }
```

响应 `201 Created`：

```json
{
  "id": "9f3c1a2b4d5e6f708192a3b4c5d6e7f8",
  "title": "准备竞赛报名材料",
  "description": "需学院盖章",
  "due_date": "2026-11-01",
  "status": "pending",
  "source": "agent",
  "created_at": "2026-10-16T08:00:00+00:00",
  "updated_at": "2026-10-16T08:00:00+00:00"
}
```

除 `title` 外均可省略。省略后的默认值：`description=""`、`due_date=null`、`status="pending"`、`source="manual"`。

### 4.2 查询任务列表

```http
GET /api/tasks?status=pending&limit=50&offset=0
```

响应 `200 OK`：

```json
{ "items": [ { "...task..." } ], "total": 12, "limit": 50, "offset": 0 }
```

注意响应是对象信封，不是裸数组。`status` 可选；`limit` 默认 50、范围 1 至 200；`offset` 默认 0；排序为 `created_at` 倒序。

### 4.3 查询单个任务

```http
GET /api/tasks/{task_id}
```

`200` 返回单个任务对象；不存在返回 `404`。

### 4.4 更新任务

```http
PATCH /api/tasks/{task_id}
Content-Type: application/json

{ "status": "done" }
```

`200` 返回更新后的完整对象。只更新请求体中显式出现的字段；传 `{"due_date": null}` 可清空截止日期；`id` 与 `created_at` 不可修改。

### 4.5 删除任务

```http
DELETE /api/tasks/{task_id}
```

返回 `204 No Content`，响应体为空，前端不应调用 `.json()`。

---

## 五、能力评估：能否接住 Agent 生成的任务

| 能力 | 现状 | 结论 |
| --- | --- | --- |
| 接收单条任务 | `POST /api/tasks` | 能 |
| 落盘保存 | JSON 原子写 | 能 |
| 查看任务列表 | `GET /api/tasks` | 能 |
| 查看单条任务 | `GET /api/tasks/{task_id}` | 能 |
| 更新任务状态 | `PATCH /api/tasks/{task_id}` | 能 |
| 删除任务 | `DELETE /api/tasks/{task_id}` | 能 |
| 批量创建（一个计划包含多条任务） | 一次只接收 1 条 | 不能，且无原子性，前端循环调用时部分失败会留下半个计划 |
| 任务归属（属于哪个学生） | 无 `owner` 字段，项目无用户系统 | 不能，所有客户端共享同一份列表 |
| 关联知识来源 | `source` 只有粗粒度枚举 | 不能，无法回溯任务出自哪份资料 |
| 草稿或待确认状态 | `POST` 即落盘 | 不能，撑不起「用户确认后再保存」 |
| 任务优先级与排序 | 无 `priority` 字段 | 不能 |

---

## 六、新增任务管理功能最少需要改哪些文件

需要先澄清一点：如果「新增」指的是从 `main` 出发补齐任务能力，那么代码已经写完，不需要新写任何文件，只需把两个提交合入 `main`。变更总规模为 9 个文件、+1833 行，其中 6 个是全新文件、1 个是审查文档、2 个是极小改动。

若只做「把 Agent 生成的任务落库」这一件事，最少改动如下：

| 场景 | 需改文件 | 说明 |
| --- | --- | --- |
| Agent 运行在服务端进程内（推荐） | 0 个新文件 | 直接 `from backend.tasks.router import get_task_store`，复用同一个存储实例，不走 HTTP |
| Agent 通过 HTTP 调用 | 0 个新文件 | `POST /api/tasks` 并带 `"source": "agent"`，接口已就绪 |
| 需要批量创建 | `store.py` + `models.py` + `router.py` + 两个测试文件 | 属新增接口，需先确认契约 |
| 需要任务归属或知识来源 | `store.py` + `models.py` + 测试 | 需先确认字段契约 |
| 需要更换持久化后端 | 仅 `store.py` | 分层设计的收益：`TaskStore` 方法签名不变，上层与全部测试无需改动 |

---

## 七、可能与聊天、流式输出冲突的地方

| 冲突点 | 风险 | 事实依据 |
| --- | --- | --- |
| `backend/main.py` | 中。本人改动为 L15 增加一行 import 与 L51 增加一行 `app.include_router(tasks_router)`，共 3 行。`feat/agent` 若也要注册路由，会改同一文件同一区域 | `git diff main feat/task-api -- backend/main.py` |
| `/api/chat` 的 SSE 流式输出 | 零冲突。任务接口挂在独立 `APIRouter`、独立路径前缀 `/api/tasks`，未改动 `/api/chat` 任何一行 | `test_main.py`(7) 与 `test_rag_chat.py`(11) 全部通过；OpenAPI 路由表确认 `/api/chat` 原样保留 |
| `/api/chat` 的请求与响应格式 | 未改动。`Message`、`ChatRequest`、RAG 提示词组装、SSE 事件格式、`[DONE]` 结束标记、模型名均保持原样 | 同上 |
| `frontend/src/App.tsx` | 归 `feat/task-ui-zyhh` 负责，本人不涉及 | 无 |
| `.gitignore` | 低。仅增加 2 行（`data/tasks.json`） | 无 |
| `data/tasks.json` | 无冲突，已被忽略 | 无 |
| `backend/knowledge/**` | 零冲突，任务模块不依赖它 | 无 |
| `main` 上不存在任务模块 | 高。这是当前最大的协同风险：Agent 负责人若基于 `main` 开发，看不到接口，可能重复实现 | `git ls-tree -r --name-only main -- backend/tasks` 返回空 |

---

## 八、需要开发的功能和风险

| 优先级 | 功能 | 风险与说明 |
| --- | --- | --- |
| 高 | 先合分支：将 `feat/task-api` 合入 `main`，或让 Agent 负责人从该分支拉出开发分支 | 不解决则双方并行实现，产生重复代码 |
| 中 | 批量创建与原子性：一个计划一次提交，全成功或全失败 | 会新增接口路径，属破坏性扩展，需先确认契约 |
| 中 | 任务归属 `owner` | 项目无用户系统，定义归属即定义用户来源 |
| 中 | 知识来源关联（会话标识、来源文档、引用） | 需与 `feat/agent` 约定字段，避免各写一套 |
| 低 | 草稿或待确认状态 | 决定「用户确认」落在前端还是后端 |
| 低 | 存储升级（多 worker 或共享存储） | 只需改 `store.py`，上层与全部测试无需改动 |

### 已实测确认的缺陷

1. `PATCH` 传 `null` 返回 `400` 而非 `422`。`title`、`description`、`status`、`source` 四个字段均如此。前端表单把清空字段绑定为 `null` 时会直接触发。成因是 `UpdateTaskRequest` 把字段声明为可空，Pydantic 放行后由领域层抛出 `TypeError`，最终被映射为 `400`。
2. `due_date` 空串语义在两层之间相反：`PATCH {"due_date": ""}` 返回 `200` 并静默清空，而 `store.update(due_date="")` 抛出 `ValueError`。根因是日期校验逻辑在 `models.py` 与 `store.py` 中各写了一份。

### 其他风险

`TaskStorageError` 未映射到 HTTP，存储损坏时会返回 500，且存储实例保持未创建状态导致每个请求重复失败（推断，未实测）。JSON 持久化存在单进程、O(n) 写入、数据不共享三项固有限制。

---

## 九、验证证据

新增任务模块的测试执行结果（真实运行，未省略失败项）：

| 命令 | 结果 |
| --- | --- |
| `python -B -m unittest backend.tasks.test_task_store`（系统 Python，零第三方依赖） | 通过，Ran 51 |
| `.venv\Scripts\python.exe -B -m unittest backend.tasks.test_task_router` | 通过，Ran 37 |
| 两个模块合并运行 | 通过，Ran 88 |

回归验证（改动未破坏既有功能）：

| 模块 | 结果 |
| --- | --- |
| `backend.test_main` | 通过，Ran 7（聊天接口） |
| `backend.test_rag_chat` | 通过，Ran 11 |
| `backend.knowledge.*` 共 11 个模块 | 通过，合计 Ran 148 |
| 以上 13 个模块合并一次运行 | 通过，Ran 167 |
| `backend.knowledge.test_embedding` | Ran 8，1 个错误（缺少 fastembed，与本改动无关） |

实测语句覆盖率（自制探针，非 coverage.py）：`store.py` 93%、`models.py` 98%、`router.py` 80%。未覆盖分支的完整清单见 `docs/task-api-code-review.md`。

---

## 声明

- 本报告只做审查，未新增任何接口，未修改任何代码，未新建数据库
- 核对过程全部为只读操作（`git ls-tree` / `git show` / `git diff` / 读取工作区文件），未切换分支
- 未调用任何真实大模型 API，未读取或输出任何密钥
- 标注为「未实测」「待验证」「推断」的内容均未经实际验证，不应视为已通过