# 前端可复用组件梳理

| 项目 | 内容 |
| --- | --- |
| 日期 | 2026-10-16 |
| 分支 | `feat/task-ui-zyhh` |
| 依据 | `frontend/src` 实际代码（`App.tsx` 327 行 / `index.css` 448 行 / `main.tsx` 10 行） |
| 性质 | **只读梳理**，未抽取组件、未修改任何业务代码 |

---

## 1. 结论摘要

**当前前端真正意义上的"可复用组件"数量为 0。** 全部 UI 都是 `App.tsx` 内联 JSX，没有 `components/` 目录，没有 props 接口，没有 hooks 目录，也没有共享类型文件。因此这份梳理分两部分：

- **A. 可从 `App.tsx` 抽取的复用单元**（已有实现，抽取后可被任务 UI 复用）
- **B. 需要新建的通用原子组件与任务域组件**（暂不存在）

抽取 A 类会改动 `App.tsx`，属于聊天 UI 的地盘，**冲突风险高**；新建 B 类只增加文件，风险低。建议先做 B 类，A 类等与聊天 UI 负责人对齐后再动。

---

## 2. A 类：可从 `App.tsx` 抽取的复用单元

| # | 现有内联片段 | 位置 | 抽取目标 | 谁可复用 | 冲突风险 |
| --- | --- | --- | --- | --- | --- |
| A1 | 自动滚底副作用 | `App.tsx:20-31` | `useAutoScroll(ref, deps)` hook | 任务列表、计划预览（长列表/长计划同样需要滚底） | 低（纯逻辑，可原样复制到新 hook 文件） |
| A2 | SSE 流式解析（reader + `\n\n` 切分 + `data:` 提取 + `[DONE]`） | `App.tsx:87-150` | `services/streamClient.ts` 的 `streamSse(url, body, {onDelta, signal})` | **计划生成若采用流式返回可整套复用**（Agent 逐步生成计划时体验更好） | 低（新文件），但需保持与现有手写实现行为一致 |
| A3 | SSE 事件结构断言 | `App.tsx:105-108` | 同上，补运行时校验 | 所有流式接口 | 低 |
| A4 | 请求失败文案拼装 | `App.tsx:161-172` | `buildErrorMessage(partial, reason)` | 所有接口的错误展示 | 低 |
| A5 | 复制到剪贴板 + 1.5s "已复制" 瞬时反馈 | `App.tsx:194-207` + state `copiedMessageIndex`(15) | `useCopyFeedback()` hook + `CopyButton` 组件 | 任务详情、计划步骤、计划导出文本 | 中（需重命名 state，会碰 `App.tsx`） |
| A6 | 消息气泡（user 纯文本 / ai 走 Markdown） | `App.tsx:240-271` | `MessageBubble` 组件 | 任务讨论区、计划说明展示 | 中高（聊天核心渲染，改动需回归测试） |
| A7 | Markdown 渲染块（`ReactMarkdown` + `remarkGfm`） | `App.tsx:254` | `MarkdownBlock` 组件 | **计划预览/计划步骤的富文本**（Agent 生成的计划天然是 Markdown） | 低（新增组件，`App.tsx` 内改为引用即可） |
| A8 | 空 AI 气泡隐藏逻辑 | `App.tsx:237-239` | 随 `MessageList` 一起抽出 | 任何"占位+流式填充"列表 | 中高（与占位索引机制 `placeholderIndex` 耦合，抽错会破坏流式追加） |
| A9 | 消息列表容器 | `App.tsx:233-285` | `MessageList` / `ScrollContainer` | 任务列表可视作同一类"可滚动卡片列表" | 中高 |
| A10 | "AI正在思考..."提示 | `App.tsx:275-281` | `TypingIndicator` / `LoadingHint` | 计划生成中的等待态 | 低 |
| A11 | 侧边栏按钮（新建/清空） | `App.tsx:212-226` | `SidebarButton` + `Sidebar` 容器 | 任务视图的侧栏导航、筛选按钮 | 中（需给侧栏加导航项，必然改 `App.tsx`） |
| A12 | 输入区（受控 textarea + Enter/Shift+Enter + `isComposing` 中文输入法判断 + 发送/停止按钮） | `App.tsx:288-319` | `ChatInput` 组件（含 `onSubmit` / `onStop` / `disabled` props） | 任务编辑区的文本输入（如"任务备注""自定义步骤"） | 中高（聊天主交互，必须回归测试） |

其中 **A12 的 `isComposing` 判断（`App.tsx:301`）和 A2 的 SSE 解析是两处最值得复用的既有资产**——中文输入法下的回车行为、流式增量拼接都属于容易踩坑且已被验证过的逻辑（注：是否真在运行中验证过，见第 5 节）。

---

## 3. B 类之一：需要新建的通用原子组件

这些是聊天 UI 与任务 UI 都会用到、但当前完全不存在的基础件。建议放 `frontend/src/components/common/`：

| 组件 | 用途 | 复用场景 |
| --- | --- | --- |
| `Button` | 统一主/次/危险/幽灵四种变体 | 现状是全局 `button` 选择器（`index.css:380-396`）在控制所有按钮，新增组件必须绕开它 |
| `Card` / `Panel` | 统一圆角卡片容器 | 聊天气泡、计划卡片、任务卡片 |
| `Badge` / `StatusTag` | 状态标签（带颜色语义） | 任务状态、计划状态、来源标注 |
| `Modal` / `ConfirmDialog` | 确认对话框 | 计划确认（第 ④ 环）、清空对话二次确认 |
| `EmptyState` | 空态占位 | 空任务列表、无检索结果 |
| `Spinner` / `Skeleton` | 加载态 | 计划生成中、列表加载中 |
| `Select` / `Dropdown` | 下拉选择 | 任务状态切换（第 ⑦ 环）、按专业/年级筛选 |
| `ListItem` | 可点击列表行 | 任务列表项、计划步骤项 |
| `Toast` / `InlineFeedback` | 瞬时反馈 | 复用 A5 的"已复制"模式，用于"已保存/已更新" |

## 4. B 类之二：任务域组件（本分支职责范围）

| 组件 | 对应流程环节 | 依赖 |
| --- | --- | --- |
| `PlanPreview` | ③ 用户预览 | 类型定义 + `MarkdownBlock` + `Card` |
| `PlanEditor` | ③ 用户编辑 | 上述 + 受控输入（可复用 `ChatInput` 思路） |
| `PlanStepItem` | ③ 步骤级增删改 | `ListItem` + `Button` |
| `PlanConfirmBar` | ④ 用户确认 | `Button` + `ConfirmDialog` |
| `TaskList` / `TaskItem` | ⑥ 查看任务列表 | `ListItem` + `EmptyState` |
| `TaskStatusSelect` | ⑦ 更新任务状态 | `Select` / `StatusTag` |
| `types/task.ts` | 全流程契约 | 无（纯类型） |
| `services/taskApi.ts` | ⑤⑥⑦ 数据读写 | 无（fetch 封装） |

### 组件 ↔ 流程环节映射

| 流程环节 | 复用现有（A 类） | 新建（B 类） |
| --- | --- | --- |
| ① 知识检索 | A6 / A7（展示带来源的答案） | 检索结果来源标签（`StatusTag`） |
| ② Agent 生成计划 | A2 / A10（流式生成 + 等待态） | ——（后端职责） |
| ③ 预览 / 编辑 | A7 复用 | `PlanPreview` / `PlanEditor` / `PlanStepItem` |
| ④ 确认 | A5（反馈模式） | `PlanConfirmBar` / `ConfirmDialog` |
| ⑤ 保存任务 | A4（错误文案） | `services/taskApi.ts` |
| ⑥ 查看列表 | A1（滚底）/ A9（列表容器思路） | `TaskList` / `TaskItem` / `EmptyState` |
| ⑦ 更新状态 | A5（瞬时反馈） | `TaskStatusSelect` / `StatusTag` |

---

## 5. 复用障碍与约定（重要）

1. **全局 CSS 选择器会污染复用组件**：`index.css` 的 `button`(380-396)、`textarea`(344-368)、`h1`(78-84) 都是无作用域全局样式。任何新组件的 `<button>` 都会继承 `width:100px` + `margin-left:15px` + 蓝色底。**约定：任务 UI 使用独立 CSS 文件 + `.task-*` / `.plan-*` 类名前缀，不改动现有选择器。**
2. **网络出口硬编码**：唯一请求是 `App.tsx:61-62` 的 `http://127.0.0.1:8000/api/chat`，没有 base URL 常量、没有 service 层。新增任务接口必须自建 `services/` 层，**不要**把任务请求塞进 `App.tsx`。
3. **无共享类型目录**：全项目唯一类型是组件内局部 `type Message`（`App.tsx:8-11`），且 `role: string` 而非联合类型。任务类型应新建 `types/task.ts` 并使用严格联合类型，不要复制这种松类型风格。
4. **无路由**：`package.json` 无 router 依赖。在不新增依赖的前提下，多视图只能用条件渲染 + 局部 state 实现。
5. **A 类抽取需协调**：`App.tsx` 是唯一业务文件，谁改谁冲突。约定只做"抽取不改行为"的机械搬移，抽取后必须跑一遍聊天回归用例（见测试表 FE-xx）。
6. **待确认**：A 类各片段的"可复用性"是静态阅读得出的判断，**没有运行验证**（当前环境无 npm、无 node_modules，前端从未启动过，详见审查报告 2.3）。尤其 A2 的 SSE 解析、A8 的占位索引机制、A12 的输入法判断，都需要在环境就绪后实测确认后再抽取。

---

## 6. 建议的推进顺序

1. 先建 `types/task.ts` + `services/taskApi.ts`（零依赖、零冲突）。
2. 再建 `components/common/` 中的 `Button` / `Card` / `Badge` / `EmptyState`（原子件，风险低）。
3. 然后做任务域组件（③④⑥⑦）。
4. 最后才考虑 A 类抽取，且一次只抽一个、配套回归。

