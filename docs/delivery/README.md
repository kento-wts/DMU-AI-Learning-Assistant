# 交付材料目录

| 项目 | 内容 |
| --- | --- |
| 日期 | 2026-10-16 |
| 分支 | `feat/task-ui-zyhh` |
| 阶段 | 审查与准备阶段（**尚未开始功能开发**） |

本目录用于集中存放"任务管理前端 + 测试/交付"职责范围内的交付材料，避免材料散落在仓库根目录或各人本地。

---

## 1. 目录结构

```
docs/
├── 2026-10-16-code-review-task-ui-zyhh.md     ← 代码审查报告（已完成）
├── review/
│   └── frontend-component-inventory.md        ← 前端可复用组件梳理（已完成）
├── test/
│   └── frontend-test-matrix.md                ← 测试用例表（已完成，结果待填）
└── delivery/                                  ← 本目录
    ├── README.md                              ← 交付清单与索引（本文件）
    ├── environment/
    │   └── README.md                          ← 环境说明（待补）
    └── demo/
        └── README.md                          ← 演示材料说明（待补）
```

---

## 2. 交付物清单

| # | 交付物 | 对应职责 | 位置 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 代码审查报告 | 集成问题记录 | `docs/2026-10-16-code-review-task-ui-zyhh.md` | **已完成**（已推送 `9c3334f`） |
| 2 | 前端可复用组件梳理 | 任务管理前端 | `docs/review/frontend-component-inventory.md` | **已完成**（未提交） |
| 3 | 测试用例表 | 基础测试 | `docs/test/frontend-test-matrix.md` | **已完成**（未提交；执行结果全部为空，待环境就绪后填写） |
| 4 | 环境说明 | 环境说明 | `docs/delivery/environment/README.md` | **待补**（依赖负责人确认安装授权） |
| 5 | 启动验证记录 | 项目启动验证 | `docs/delivery/environment/` | **待补**（当前被环境阻塞） |
| 6 | 演示材料 | 演示材料整理 | `docs/delivery/demo/` | **待补**（功能未开发） |
| 7 | 集成问题清单 | 集成问题记录 | 已并入审查报告第 2.4 节 | 已完成（初版） |

---

## 3. 各子目录说明

### `environment/` —— 环境说明

存放内容：技术栈与版本、依赖安装步骤、环境变量配置说明、启动命令、已知环境阻塞点。

已确认的事实（可先行填写）：

- 前端：React 19 + TypeScript 5.8 + Vite 6；`package.json` 仅 `dev` / `build` / `preview` 三个脚本，**无 lint / test 脚本**
- 后端：Python 3.13.9；`requirements.txt` 共 7 项（fastapi、uvicorn、openai、python-dotenv、pypdf、fastembed、chromadb）
- 后端启动强依赖 `DEEPSEEK_API_KEY`（`backend/main.py:23-26`，模块级校验，缺失即抛错）
- 向量库落盘位置：`<repo>/data/chroma`（`.gitignore` 已忽略）
- **阻塞点**：本机无 npm；后端依赖全部未安装；无 `.env` / `.env.example`

### `demo/` —— 演示材料

存放内容：演示脚本（分步骤讲稿）、截图、录屏、演示用测试数据、演示环境检查清单。

建议围绕目标流程组织演示主线：**知识检索 → Agent 生成任务计划 → 用户预览/编辑 → 用户确认 → 保存任务 → 查看任务列表 → 更新任务状态**。

---

## 4. 交付判定标准（建议）

| 交付物 | 判定标准 |
| --- | --- |
| 审查报告 | 基于真实代码与真实命令结果；未验证项明确标注 |
| 组件梳理 | 每个可复用单元标注真实文件与行号，并标注冲突风险 |
| 测试表 | 每条用例有可复现步骤与预期；结果列只填写真实执行过的内容 |
| 环境说明 | 他人按文档可从零跑通前后端 |
| 演示材料 | 能完整走通上述七个环节，或明确标注哪些环节为 mock |

---

## 5. 待负责人确认（阻塞交付）

1. 是否允许安装 Node/npm 与 Python 依赖（否则交付物 4、5 无法完成）
2. 是否允许写入 `data/chroma` 向量库、是否允许联网下载 embedding 模型
3. 是否允许真实调用 DeepSeek API 用于端到端验证与演示
4. 任务数据契约与接口清单（决定交付物 6 的演示形态）
5. 是否引入前端新依赖（router / 测试框架）

