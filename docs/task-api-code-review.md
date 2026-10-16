# 任务管理模块 · 第二阶段代码审查报告

| 项目 | 内容 |
| --- | --- |
| 审查对象 | `backend/tasks/**`（本阶段新增 6 个文件） + `backend/main.py`、`.gitignore` 的小幅改动 |
| 分支 | `feat/task-api` |
| 被审提交 | `defd3cb` |
| 审查范围 | 仅本人本阶段产出的代码，不含 `backend/knowledge/**`、`frontend/**`、Agent 主流程 |
| 审查方式 | 逐行只读阅读 + 真实测试执行 + 自制 `sys.settrace` 语句覆盖率探针 |
| 日期 | 2026-10-16 |

> 本报告不修改任何业务代码、不改变现有接口、不新建数据库。
> 审查过程中所有验证均写入系统临时目录，未污染仓库数据（`data/` 全程不存在，`git status` 全程干净）。

---

## 一、审查范围界定

| 属于本次审查 | 不属于本次审查 |
| --- | --- |
| `backend/tasks/__init__.py`（47 行，新） | `backend/knowledge/**`（他人代码，未改未审） |
| `backend/tasks/store.py`（401 行，新） | `frontend/**`（归 `feat/task-ui-zyhh`） |
| `backend/tasks/models.py`（139 行，新） | `backend/rag_chat.py`、`backend/test_main.py` 等既有文件 |
| `backend/tasks/router.py`（168 行，新） | Agent 主流程（他人负责） |
| `backend/tasks/test_task_store.py`（470 行，新） | |
| `backend/tasks/test_task_router.py`（363 行，新） | |
| `backend/main.py`（**+3 行**）、`.gitignore`（**+2 行**） | |

---

## 二、当前实现（逐文件）

### 2.1 `store.py` — 领域层（纯标准库，零第三方依赖）

| 机制 | 位置 | 实现 |
| --- | --- | --- |
| 值对象 | `Task`，L61-76 | `@dataclass(frozen=True)`，`to_dict()` 用 `asdict()` |
| 存储 | `TaskStore._tasks` L90 | 内存 `dict[str, Task]` |
| 持久化 | `_save` L242-253 | 全量重写 -> 写 `.tmp` -> `os.replace()` 原子替换 |
| 反序列化 | `_load` L212-240 + `_task_from_record` L357-379 | 逐条强校验，任何异常转 `TaskStorageError` |
| 并发 | `threading.RLock` L89 | 所有读写在锁内 |
| 写失败回滚 | L151-155 / L189-193 / L206-210 | 内存先改，写盘失败则还原 |
| 校验器 | L267-354（7 个 `_validate_*`） | 类型错 `TypeError`，取值错 `ValueError` |

### 2.2 `models.py` — HTTP 层模型

`CreateTaskRequest`（L24-50）、`UpdateTaskRequest`（L53-83）、`TaskResponse`（L86-100）、`TaskListResponse`（L103-109）、`TaskStatus` / `TaskSource` 两个 `Literal`（L18-19）、`_normalise_due_date`（L112-129）。

### 2.3 `router.py` — HTTP 层路由

`prefix="/api/tasks"`（L27）、`get_task_store()` 双重检查锁单例（L33-45）、`TaskStoreDep`（L48）、两个异常映射辅助（L51-56）、5 个端点（L59-160）。

### 2.4 已实现的接口

| 方法 | 路径 | 成功码 | 错误码 |
| --- | --- | --- | --- |
| `POST` | `/api/tasks` | `201` | `422` |
| `GET` | `/api/tasks` | `200` | `422` |
| `GET` | `/api/tasks/{task_id}` | `200` | `404` / `400` |
| `PATCH` | `/api/tasks/{task_id}` | `200` | `404` / `400` / `422` |
| `DELETE` | `/api/tasks/{task_id}` | `204` | `404` / `400` |

### 2.5 对既有文件的改动

`main.py`：仅一行 import 与一行 `app.include_router(tasks_router)`；启动逻辑与聊天流程**逐字节未动**（`git diff` 核对，且 `test_main.py` / `test_rag_chat.py` 全部通过）。

`.gitignore`：在 `data/chroma/` 之后追加 `data/tasks.json`。

---

## 三、验证结果

### 3.1 实际执行的命令与真实结果

| # | 命令 | 结果 |
| --- | --- | --- |
| 1 | `python -B -m unittest backend.tasks.test_task_store`（系统 Python，零第三方依赖） | 通过，`Ran 51` |
| 2 | `.venv\Scripts\python.exe -B -m unittest backend.tasks.test_task_router` | 通过，`Ran 37` |
| 3 | 两个模块合并运行 | 通过，`Ran 88` |
| 4 | 运行前后检查 `data/` 目录 | 前后均为 `False`，测试使用临时目录，未污染仓库数据 |
| 5 | `git status --porcelain` | 为空，审查过程零改动 |
| 6 | 自制覆盖率探针（`sys.settrace` + `threading.settrace`） | 88 个测试全部通过，覆盖率见 3.2 |

```powershell
# 在仓库根目录执行
python -B -m unittest backend.tasks.test_task_store
.\backend\.venv\Scripts\python.exe -B -m unittest backend.tasks.test_task_router
.\backend\.venv\Scripts\python.exe -B -m unittest backend.tasks.test_task_store backend.tasks.test_task_router
```

### 3.2 实测语句覆盖率

> 使用自写探针而非 `coverage.py`，以避免为本轮审查安装依赖。
> **首次测量结果不足采信**，因为发现两个测量缺陷并已修正：
> 1. `sys.settrace` 只跟踪当前线程，而 FastAPI 同步端点运行在 anyio 线程池中，导致 `router.py` 被误报为 38%；
> 2. 探针把函数 docstring 当成了可执行语句，产生大量假「未覆盖」。
> 下表为修正后（加入 `threading.settrace`、排除纯字面量语句）的结果。

| 文件 | 可执行语句覆盖 | 未执行行 |
| --- | --- | --- |
| `backend/tasks/__init__.py` | 2/2（100%） | 无 |
| `backend/tasks/models.py` | 66/67（98%） | `119` |
| `backend/tasks/store.py` | 200/215（93%） | `154,155,174,180,192,193,209,210,220,253,264,327,347,352,359` |
| `backend/tasks/router.py` | 46/57（80%） | `38,40,41,42,43,45,75,94,117,141,158` |

### 3.3 未执行行分类解读

#### A 类：预期内的防御性代码，可接受不覆盖

| 行 | 内容 |
| --- | --- |
| `store.py` 154-155 / 192-193 / 209-210 | `create` / `update` / `delete` 的写盘失败回滚分支 |
| `store.py` 220 / 253 | 读盘 `OSError` / 写盘失败转 `TaskStorageError` |
| `router.py` 75 / 94 / 117 / 158 | `create` / `list` / `get` / `delete` 的 400 分支，经 HTTP 实际不可达（Pydantic 已拦截） |

#### B 类：真实测试空洞，应当补齐

| # | 位置 | 说明 |
| --- | --- | --- |
| B1 | `store.py:174` | `update()` 从没测过修改 `description` |
| B2 | `store.py:180` | `update()` 从没测过修改 `source` |
| B3 | `store.py:264` | **默认时钟 `_utc_now_iso()` 从未被执行**（所有测试都注入 `AutoClock`），即生产环境的时间戳格式完全未验证 |
| B4 | `store.py:359` | 记录不是 dict（例如文件中是 `[1,2,3]`）时的报错分支 |
| B5 | `store.py:347` | 记录时间戳为空串时的报错分支 |
| B6 | `store.py:352` | 记录时间戳格式非法时的报错分支 |
| B7 | `store.py:327` | `_validate_source` 的 `TypeError`（同族的 `title` / `status` 类型错误都有覆盖） |
| B8 | `models.py:119` | `_normalise_due_date` 的「空串 -> None」分支，即问题 R2 的行为，没有任何测试固化 |
| B9 | `router.py:38,40-43,45` | **`get_task_store()` 的生产分支完全没有被测过**（所有测试都用 `dependency_overrides` 替换），真实的惰性初始化与默认存储路径从未验证 |
| B10 | `router.py:141` | `update_task` 的 400 分支，该分支在真实 HTTP 下**可触发**（见 R1），但没有测试 |

### 3.4 明确未验证的内容

| 项目 | 状态 |
| --- | --- |
| 真实 uvicorn 服务器（本轮全部使用 `TestClient`） | 未执行 |
| 在生产路径真实生成 `data/tasks.json` | 未执行（为不改动项目状态而刻意回避） |
| 多进程 / `uvicorn --workers N` 并发写 | 未验证 |
| `TaskStorageError` 在 HTTP 层的实际响应码 | 未实测，**推断**为 500 |
| `fastembed` / 向量检索相关 | 与本模块无关 |

---

## 四、发现的问题（仅限本人本阶段代码）

### R1 `PATCH` 传 `null` 返回 400 而非 422（已实测）

`PATCH {"title": null}` 返回 `400 {"detail": "title must be a string"}`，而 `PATCH {"title": 123}` 返回 `422`。

成因是本人代码内的三段链条：

1. `models.py:62-66` — `UpdateTaskRequest` 将字段声明为 `X | None = None`，Pydantic 放行 `null`
2. `router.py:132` — `model_dump(exclude_unset=True)` 将 `None` 原样下传
3. `store.py:268` — `_validate_title(None)` 抛 `TypeError`，被 `router.py:140` 映射为 `400`

`title` / `description` / `status` / `source` 四个字段均如此（`due_date` 例外，`null` 对其有语义）。前端表单把清空字段绑成 `null` 是常见写法，会直接触发。

### R2 `due_date` 空串语义在两层之间相反（已实测）

- `PATCH {"due_date": ""}` 返回 `200` 并**静默清空**
- `store.update(due_date="")` 抛 `ValueError: due_date must not be blank`

成因：`models.py:117-119` 把空串当作「未填」返回 `None`；`store.py:299-301` 把空串当作非法值抛错。根因是日期校验逻辑写了两份（`models._normalise_due_date` 与 `store._validate_due_date`），破坏了 DRY。

### R3 覆盖率空洞

见 3.3 的 B1-B10。其中 B1 / B2 / B3 / B9 是会真实走到的生产代码，却没有任何测试。

### R4 存储路径硬编码、无配置入口

`router.py:43` 直接调用 `TaskStore()`，恒用 `store.py:44` 的 `DEFAULT_STORE_PATH`。没有环境变量或配置项，部署时无法改路径，测试也只能靠 `dependency_overrides` 绕开。

### R5 `TaskStorageError` 未映射到 HTTP

`router.py` 只映射了 `TaskNotFoundError` / `TypeError` / `ValueError`。存储损坏时会变成 500，且 `_store` 保持 `None`，导致每个请求重复失败、无法自愈。（推断，未实测）

### R6 持久化的固有上限（设计权衡，非缺陷）

1. `_save` 每次全量重写整个文件（L242-251），复杂度 O(n)
2. `list()` 全量载入并排序后返回，分页在 `router.py:96` 切片，复杂度 O(n log n)
3. 只有进程内锁，隐含单进程假设

### R7 缺少批量创建

Agent 产出的是多条「任务计划」，而本模块一次只接收 1 条。前端只能循环调用，无原子性，失败会留下半个计划。

### R8 代码重复

- `AutoClock` 在 `test_task_store.py` 与 `test_task_router.py` 各写了一份
- 日期校验两处实现（即 R2 的根因）

---

## 五、开发建议

| 要解决的问题 | 需改文件 | 规模与风险 |
| --- | --- | --- |
| B1/B2/B7/B4/B5/B6 补测试空洞 | 仅 `test_task_store.py` | 零接口变更、零风险，建议立即执行 |
| B8 + R2 统一空串语义 | `models.py` + 两个测试文件 | 需先定方向：空串报错（与领域层一致）还是空串即清空（与 HTTP 现状一致） |
| R1 null -> 422 | `models.py` + `test_task_router.py` | 给 `UpdateTaskRequest` 加校验器显式拒绝 `null`，不改路径、不破坏已有 200/201 语义 |
| B3 默认时钟 | `test_task_store.py` | 增加一个不注入 clock 的测试，断言时间戳可被 `datetime.fromisoformat` 解析 |
| R4 存储路径可配置 | `router.py`（可选 `store.py`） | 增加环境变量读取 |
| R5 存储异常映射 | `router.py` + `test_task_router.py` | 增加 `TaskStorageError` -> 503 |
| R7 批量创建 | `store.py` + `models.py` + `router.py` + 两个测试文件 | 属新增能力，需负责人确认后再做 |
| R8 去重 | `models.py`、两个测试文件 | 低优先 |
| 更换持久化后端 | **仅 `store.py`** | 分层设计的收益：`TaskStore` 方法签名不变，上层与全部测试无需改动 |

**依赖关系**：本模块仅依赖 `pydantic`（HTTP 模型）与 `fastapi`（路由）；领域层零第三方依赖，`__init__.py` 刻意不导出 `router` 以维持这一点。

**冲突面**：`backend/main.py`（`feat/agent` 若也注册路由会冲突，本人仅用了 3 行）、`frontend/src/App.tsx`（不归本人）；`backend/tasks/**` 为全新目录，零冲突。

---

## 六、下一步

1. 先做零风险项：补齐 B1 / B2 / B3 / B7 等测试空洞，只动测试文件，不改接口与行为。
2. 等负责人对 R1 / R2 的行为取向拍板：
   - R1：确认前端是否会把清空字段提交为 `null`（决定紧迫度）
   - R2：空串 `due_date` 应报错还是应清空
3. R7（批量创建）必须等接口契约确认后再做，它会新增接口路径，属破坏性扩展。
4. R4 / R5 视部署方式决定；若仅单进程本地演示，可延后。

---

## 附录

**负责模块**：任务管理（数据模型、后端接口、输入校验、测试）

**Git 分支**：`feat/task-api`，被审提交 `defd3cb`，与 `origin/feat/task-api` 领先 0 / 落后 0，工作区干净

**检查过的文件**：`backend/tasks/__init__.py`、`backend/tasks/store.py`、`backend/tasks/models.py`、`backend/tasks/router.py`、`backend/tasks/test_task_store.py`、`backend/tasks/test_task_router.py`、`backend/main.py`、`.gitignore`

**发现的问题**：R1 `PATCH` 传 `null` 返回 400 而非 422；R2 `due_date` 空串两层语义相反；R3 覆盖率空洞 B1-B10；R4 存储路径硬编码；R5 `TaskStorageError` 未映射 HTTP；R6 JSON 持久化的单进程 / O(n) / 本地化上限；R7 无批量创建；R8 `AutoClock` 与日期校验重复实现

**需要其他队友配合的事项**：

1. `feat/task-ui-zyhh`：确认前端表单是否会提交 `null`（决定 R1 的紧迫度）
2. `feat/agent`：确认 Agent 写任务的接缝方式，以及是否需要批量创建与原子性
3. 负责人：R1 / R2 的行为取向，以及 R7 是否纳入范围

**本轮未做**：未修改任何业务代码、未重构、未新建数据库、未改变任何现有接口、未调用真实大模型 API、未提交或输出任何密钥。