# 任务管理：数据契约与接口清单（**草案，待确认**）

| 项目 | 内容 |
| --- | --- |
| 状态 | **草案。未确认前不得据此开发；本文不改动任何现有接口。** |
| 日期 | 2026-10-16 |
| 分支 | `feat/task-ui-zyhh` |
| 编写依据 | 实际代码：`backend/main.py`、`backend/knowledge/*`、`frontend/src/App.tsx`；以及本轮实测结论（见 `docs/test/frontend-test-matrix.md`） |
| 目的 | 把"数据契约"落到实处：谁定义字段、字段叫什么、取值有哪些、接口长什么样、错误怎么表达 |

---

## 0. 为什么需要先定这个

目标流程是：**知识检索 → Agent 生成任务计划 → 用户预览/编辑 → 用户确认 → 保存任务 → 查看任务列表 → 更新任务状态**。

这条链路上，同一个"任务"要被四个地方同时理解：

1. 后端 `planner` 从大模型拿到的结构化输出；
2. 后端 `store` 落库的字段；
3. 后端 `router` 收发的 JSON；
4. 前端 `types/task.ts` 的类型与 `services/taskApi.ts` 的调用。

四处只要有一处对不上（字段名、枚举值、时间格式、空值语义），前端就会拿到渲染不了的 `undefined`，或者保存出半截数据。**所以先冻结契约，再写代码。**

---

## 1. 数据模型

> 命名约定：JSON 字段一律 `snake_case`（与现有 `main.py` / `chroma_store.py` 的元数据风格一致）。

### 1.1 枚举

| 枚举 | 取值 | 说明 | 决策点 |
| --- | --- | --- | --- |
| `TaskStatus` | `"todo"` / `"in_progress"` / `"done"` | 机器值用英文，界面显示中文（待办/进行中/已完成） | **D1**：是否需要 `"cancelled"` / `"archived"`？ |
| `Priority` | `"low"` / `"medium"` / `"high"` | 是否真的需要优先级？ | **D2**：保留 / 去掉 / 改成 1-5 数字 |

不建议用中文当枚举值（前端做联合类型、后端做 `Literal` 都更别扭），也不建议用数字（可读性差、以后加状态会歧义）。

### 1.2 `SourceRef`——知识库引用来源

现状：检索到的 `SearchResult.metadata` / `score` **只用于拼 prompt，完全不回传前端**（实测确认，见测试表 INT-07）。"Agent 生成计划"如果要让人信服，最好带上依据。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `document_id` | `string` | 是 | 来自 chunk 元数据（`ingest.py` 写入） |
| `source` | `string` | 是 | 文件名 |
| `score` | `number` | 是 | 0–1 相似度（`chroma_store` 的 `1 - distance`） |
| `snippet` | `string` | 否 | 命中的片段（截断，如 200 字） |

**决策点 D3**：本版计划里是否要带引用来源？（带 → 演示更有说服力，但要动检索侧；不带 → 后端实现更简单）

### 1.3 `PlanStep`——计划中的一个步骤

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `title` | `string` | 是 | 步骤标题，非空，建议 ≤ 60 字 |
| `detail` | `string` | 否 | 步骤说明，允许 Markdown |
| `due_date` | `string \| null` | 否 | `"YYYY-MM-DD"`（不带时区、不带时间） |
| `estimated_minutes` | `number \| null` | 否 | 预计耗时（分钟），正整数 |
| `order` | `number` | 是 | 从 1 开始，用于排序 |

> 注意：`PlanStep` **没有 `id`**。未保存的步骤是临时对象，前端用数组下标做 key 即可；等用户确认落库后由后端生成 `Task.id`。若你希望前端能拖拽时稳定引用，可加前端本地 `tempId`（不进接口）。

**决策点 D4**：`estimated_minutes` 是否保留？大模型估时通常不准，但列表展示很直观。

### 1.4 `TaskPlan`——Agent 生成的一次计划

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `goal` | `string` | 是 | 用户输入的学习目标（回显） |
| `summary` | `string` | 是 | 计划概述（1-3 句） |
| `steps` | `PlanStep[]` | 是 | 至少 1 条，建议上限 10 条 |
| `sources` | `SourceRef[]` | 否 | 取决于 D3 |
| `model` | `string` | 是 | 生成所用的模型名，便于追溯 |
| `created_at` | `string` | 是 | ISO 8601 **带时区**，如 `"2026-10-16T22:30:00+08:00"` |

`TaskPlan` **不进数据库**（用户没确认的计划没有保存价值），只在"生成 → 预览/编辑 → 确认"之间流转。是否需要服务端暂存以支持"编辑后再确认"由 D5 决定。

**决策点 D5**：用户确认时

- 方案 A（推荐，最简单）：前端把**编辑后的 steps 整个提交**给保存接口，服务端不需要记住 plan；
- 方案 B：服务端暂存 plan，确认时只提交 `plan_id` + 差异。

A 的好处是无状态、不会过期；坏处是请求体略大（几十条步骤也没多大）。B 需要引入"草稿"生命周期。

### 1.5 `Task`——落库后的任务

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | `string` | 是 | 服务端生成（建议 UUID4 hex，与 `chroma_store` 的 id 风格一致） |
| `title` | `string` | 是 | 通常来自 `PlanStep.title` |
| `detail` | `string` | 否 | 通常来自 `PlanStep.detail` |
| `status` | `TaskStatus` | 是 | 新建时固定 `"todo"` |
| `priority` | `Priority` | 否 | 取决于 D2 |
| `due_date` | `string \| null` | 否 | `"YYYY-MM-DD"` |
| `estimated_minutes` | `number \| null` | 否 | 取决于 D4 |
| `order` | `number` | 是 | 列表排序 |
| `goal` | `string \| null` | 否 | 冗余保存来源计划的目标，便于列表分组展示 |
| `created_at` | `string` | 是 | ISO 8601 带时区 |
| `updated_at` | `string` | 是 | 同上，每次修改都更新 |

**关键决策点 D6：`PlanStep` 与 `Task` 是几对几？**

- 方案 A（推荐）：**一对一**。确认后每条步骤落成一条任务，前端列表直接展示任务。
- 方案 B：**多对一**。一次计划落成一条"父任务"，步骤存成子项（需要 `parent_id`，列表要处理展开/折叠）。

A 更贴合"查看任务列表 + 更新任务状态"的简单诉求，也更容易做演示。

**决策点 D7**：是否需要"任务归属"？当前项目**没有用户体系**（README 把 auth 列为 Future），所以本版所有任务都是全局共享的。如果要区分学生，需要先定用户标识来源。

---

## 2. 接口清单

统一前缀 `/api`，与现有 `/api/hello`、`/api/chat` 一致。**现有两条路由不做任何改动。**

| # | 方法 | 路径 | 用途 | 对应流程环节 |
| --- | --- | --- | --- | --- |
| 1 | `POST` | `/api/plan/generate` | 生成任务计划 | ② |
| 2 | `POST` | `/api/tasks` | 确认后保存任务 | ⑤ |
| 3 | `GET` | `/api/tasks` | 查看任务列表 | ⑥ |
| 4 | `PATCH` | `/api/tasks/{task_id}` | 更新任务（主要是状态） | ⑦ |
| 5 | `GET` | `/api/tasks/{task_id}` | 查看单个任务 | ⑥（可选） |
| 6 | `DELETE` | `/api/tasks/{task_id}` | 删除任务 | 无（可选，见 D8） |

**决策点 D8**：第 5、6 条要不要？不要也能完成演示主线；第 6 条（删除）会让"数据不可恢复"，演示时风险更高。

### 2.1 `POST /api/plan/generate`

```jsonc
// 请求
{
  "goal": "我想在大二下学期参加一个 A 类创新创业竞赛并拿到校级奖项",
  "filters": {            // 可选，透传给检索的 metadata_filter
    "year": 2026,
    "major": "软件工程",
    "document_type": "竞赛列表"
  }
}

// 响应 200
{
  "plan": {
    "goal": "...",
    "summary": "围绕竞赛报名-备赛-参赛三阶段拆解，共 5 步。",
    "steps": [
      { "title": "确认可参加的 A 类竞赛清单", "detail": "...", "due_date": "2026-11-01", "estimated_minutes": 120, "order": 1 }
    ],
    "sources": [ { "document_id": "...", "source": "附件1.《...竞赛列表(2026年)》.pdf", "score": 0.6837, "snippet": "..." } ],
    "model": "deepseek-v4-flash",
    "created_at": "2026-10-16T22:30:00+08:00"
  }
}
```

| 状态码 | 场景 | 响应体 |
| --- | --- | --- |
| 200 | 成功 | 如上 |
| 400 | `goal` 为空 / 全空白 | `{"detail": "goal 不能为空"}` |
| 422 | 请求体结构错误 | FastAPI 默认校验详情 |
| 502 | 上游模型失败 | `{"detail": "生成计划失败：<原因>"}` |
| 500 | 检索阶段异常 | 见下方 §3.4 |

**决策点 D9：这个接口要不要流式？**

- 方案 A（推荐）：**非流式**，一次性返回完整 JSON。简单、可靠、前端拿到即渲染。
- 方案 B：复用现有 SSE 形式边生成边显示。体验好，但要自己定义"增量 JSON 如何拼接"，且现有 SSE 的成功/错误混用模式（HTTP 200 里带 error）不宜照搬。

**决策点 D10：大模型如何产出结构化 JSON？**

- 方案 A（推荐，零新依赖）：prompt 里给出字段说明与示例，要求"只输出 JSON"，服务端 `json.loads` + Pydantic 校验；校验失败把错误回灌给模型重试一次。
- 方案 B：用 DeepSeek 的 JSON 输出模式（`response_format={"type": "json_object"}`）。**需确认** `openai 3.31.0` 客户端与 DeepSeek 该参数的实际支持情况（本轮装出来的 openai 是大版本 3.x，尚未做过该参数的实测）。

无论哪种，都必须做**服务端校验**：步骤数上限、`title` 非空、`due_date` 格式、`order` 连续。

### 2.2 `POST /api/tasks`

```jsonc
// 请求（方案 A：直接提交编辑后的步骤）
{
  "goal": "我想在大二下学期参加一个 A 类创新创业竞赛并拿到校级奖项",
  "tasks": [
    { "title": "确认可参加的 A 类竞赛清单", "detail": "...", "priority": "high", "due_date": "2026-11-01", "estimated_minutes": 120, "order": 1 }
  ]
}

// 响应 201
{ "tasks": [ { "id": "9f2c...", "title": "...", "status": "todo", "created_at": "...", "updated_at": "...", "order": 1 } ] }
```

**决策点 D11：幂等怎么保证？**（对应测试表 TASK-05"重复点击不重复创建"）

- 方案 A（推荐）：请求头 `Idempotency-Key: <uuid>`，服务端记住 5 分钟内已处理的 key，重复请求返回首次结果。
- 方案 B：前端提交时禁用按钮 + 提交后清空本地计划。**前端兜底不可靠**（刷新、双击竞态都可能绕过），所以服务端至少要有方案 A 的简化版。

### 2.3 `GET /api/tasks`

| 查询参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `status` | `TaskStatus` | 不传 | 按状态过滤 |
| `limit` | `number` | 50 | 上限建议 200 |
| `offset` | `number` | 0 | 分页 |

```jsonc
// 响应 200
{ "tasks": [ /* Task[] */ ], "total": 12 }
```

排序约定：先 `order` 升序，再 `created_at` 升序。**决策点 D12**：是否改成按 `due_date` 排序？（有截止日期的任务更关心"哪个先到期"）

### 2.4 `PATCH /api/tasks/{task_id}`

```jsonc
// 请求：只传要改的字段
{ "status": "in_progress" }

// 响应 200
{ "task": { "id": "9f2c...", "status": "in_progress", "updated_at": "...", /* 其余字段原样 */ } }
```

| 状态码 | 场景 |
| --- | --- |
| 200 | 成功 |
| 404 | `task_id` 不存在 → `{"detail": "任务不存在"}` |
| 422 | `status` 不是合法枚举值 / 请求体为空 |

用 `PATCH` 而非 `PUT`：前端只改状态，不应该被迫回传整个对象——**回传整个对象会引入"用旧数据覆盖新数据"的竞态**。

---

## 3. 统一约定（这些最好一次定死）

### 3.1 错误体

**决策点 D13**：沿用 FastAPI 默认的 `{"detail": "..."}`，还是改成结构化 `{"error": {"code": "TASK_NOT_FOUND", "message": "..."}}`？

- 沿用默认：零成本、与现有 400 行为一致（实测 `{"detail":"请求中没有 user 消息"}`）。
- 结构化：前端能做分支处理（比如"任务不存在"自动刷新列表），但要统一改造错误处理。

### 3.2 时间格式

- `due_date`：`"YYYY-MM-DD"`，**不带时间、不带时区**（用户填的是日期，不是时刻）。
- `created_at` / `updated_at`：ISO 8601 **带时区偏移**。

不要用 Unix 时间戳（前端要额外转换，且调试时不可读）。

### 3.3 类型严格性——**不要复制现有聊天接口的松类型**

现有 `/api/chat` 的契约是 `role: string`（任意字符串）、SSE 里成功与错误混用（HTTP 200 携带 error 事件）、客户端可注入 `role:"system"`（已实测证实）。这些都**不应被任务接口继承**：

- 枚举一律用 `Literal`（后端）/ 联合类型（前端），不用裸 `str`；
- 错误走 HTTP 状态码 + 统一错误体，不在 200 响应里藏错误。

### 3.4 检索阶段异常要有兜底

实测确认：当前 `/api/chat` 在检索阶段抛异常时会返回 **HTTP 500 + 纯文本 `Internal Server Error`**（未捕获的 `EmbeddingError`）。`/api/plan/generate` 依赖同一条检索链路，**必须显式捕获并返回结构化错误**，否则前端只能显示"未知错误"。

---

## 4. 持久化方案

| 方案 | 实现 | 优点 | 缺点 |
| --- | --- | --- | --- |
| **A（推荐）SQLite 文件** | 标准库 `sqlite3`，文件建议 `<repo>/data/tasks.db`（与 `data/chroma` 同级，`.gitignore` 已覆盖 `data/chroma/`，需补一条 `data/tasks.db`） | 零新依赖；支持按状态查询与原子更新；进程重启不丢 | 需要引入表结构（属"新建数据库"，需你解除限制） |
| B JSON 文件 | `json` + 文件读写 | 最简单，可直接肉眼查看 | 并发写有风险；查询/更新要全量读入 |
| C 内存字典 | `dict` | 零成本 | **重启即丢**，演示刷新后端就没了，不适合交付 |

**决策点 D14**：选哪个？若选 A，需要你确认解除"本阶段不新建数据库"的限制，并确认表结构由我提出、你审核。

---

## 5. 与前端类型的一一对应

契约冻结后，前端 `src/types/task.ts` 直接照抄本文 1.1–1.5 节，做到：

```ts
export type TaskStatus = "todo" | "in_progress" | "done";
export interface PlanStep { title: string; detail?: string; due_date?: string | null; estimated_minutes?: number | null; order: number; }
export interface TaskPlan { goal: string; summary: string; steps: PlanStep[]; sources?: SourceRef[]; model: string; created_at: string; }
export interface Task { id: string; title: string; detail?: string; status: TaskStatus; due_date?: string | null; order: number; created_at: string; updated_at: string; }
```

**注意 `role: string` 的教训**：字段类型必须是联合类型而非 `string`，否则编译期发现不了拼写错误（现有 `Message` 类型就是反例）。

---

## 6. 需要你拍板的决策点汇总

| 编号 | 决策点 | 我的建议 |
| --- | --- | --- |
| D1 | `TaskStatus` 是否要 `cancelled` / `archived` | 不要，三态足够 |
| D2 | 是否需要优先级 | 保留（列表展示直观），可后置实现 |
| D3 | 计划是否带回知识库引用来源 | 带（演示说服力强，且能解决"检索不可见"问题） |
| D4 | 是否保留 `estimated_minutes` | 保留但允许为空 |
| D5 | 确认时是提交整个 steps 还是只提交 `plan_id` | 提交整个 steps（无状态，最简单） |
| D6 | `PlanStep` 与 `Task` 的关系 | 一对一 |
| D7 | 是否需要任务归属/用户标识 | 本版不做（项目无用户体系） |
| D8 | 是否需要单条查询与删除接口 | 单条查询可不做；删除建议延后 |
| D9 | 生成计划是否流式 | 非流式（可靠优先） |
| D10 | 结构化输出怎么做 | prompt 约束 JSON + 服务端 Pydantic 校验（零新依赖） |
| D11 | 保存接口如何幂等 | 服务端 `Idempotency-Key` |
| D12 | 列表排序 | 先 `order`，可加 `due_date` |
| D13 | 错误体格式 | 沿用 `{"detail": "..."}`（与现有接口一致） |
| D14 | 持久化方案 | SQLite 文件（`data/tasks.db`） |

**确认方式建议**：直接回复"D1–D14 全部按建议"或逐条给出不同意见。契约冻结后再动手写代码；本文确认前，`/api/chat` 等现有接口与本草案均不产生任何变更。
