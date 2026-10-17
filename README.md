# DMU AI Learning Assistant

大连海事大学 AI 学习助手。当前实现的是**基于本地知识库的 RAG 问答**：
问题先在学校文件里检索，再把检索到的原文片段连同**来源、年份**一起交给模型作答。

## 技术栈

| 层 | 组成 |
| --- | --- |
| 前端 | React 19 + TypeScript + Vite 6 |
| 后端 | FastAPI（Python 3.13） |
| 向量检索 | Chroma（本地持久化）+ fastembed 本地模型 `BAAI/bge-small-zh-v1.5`（512 维，**不需要 API Key**） |
| 文本生成 | DeepSeek API |

## 目录结构

```
backend/
  main.py                  FastAPI 入口：/api/hello、/api/chat（SSE 流式）
  rag_chat.py              非流式的 RAG 会话封装（当前 main.py 未使用）
  knowledge/
    documents/              10 份已评审的知识材料 PDF
    pdf_loader.py           PDF → 文本（NFKC 归一化）
    chunker.py              文本 → 切片（段落优先，上限 1200 字符）
    embedding.py            文本 → 向量（本地模型）
    chroma_store.py         Chroma 读写与相似度检索
    retriever.py            检索编排
    query_filters.py        从问题中的显式年份生成检索过滤条件
    prompt_builder.py       检索结果 → 带来源的 prompt
    ingest.py               单份 PDF 的完整入库流程
    ingest_document.py       单文件入库 CLI（需要手工传全部元数据）
    build_index.py          ★ PDF → 向量库（批量、幂等）
    export_chunks.py        ★ PDF → 文本 + 切片文件
    evaluate_retrieval.py   评估集诊断脚本
    evaluation_dataset.json 带标准答案的问题集
frontend/                   React 聊天界面
tools/rag_verification/     只读验证脚本与实验存档
data/
  chroma/                   向量库（已提交，克隆后可直接运行）
  exports/                  抽取文本与切片文件（已提交）
```

## 环境要求

- Python 3.13，依赖见 `backend/requirements.txt`
- Node ≥18（Vite 6 要求）
- 一个 DeepSeek API Key

## 快速开始

```bash
# 1. 后端依赖
python -m pip install -r backend/requirements.txt

# 2. 在仓库根目录放 .env，内容为：
#    DEEPSEEK_API_KEY=<你的 key>

# 3. 构建向量库（仓库里已带 data/chroma，仅在需要重建时执行）
python -m backend.knowledge.build_index

# 4. 启动后端（端口必须是 8000，前端把地址写死在这里）
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

# 5. 前端
cd frontend
npm ci
npm run dev
```

浏览器打开 http://127.0.0.1:5173 。接口文档在 http://127.0.0.1:8000/docs 。

首次构建索引时 fastembed 会自动下载向量模型（约 90 MB）。可用 `EMBEDDING_MODEL` 换模型、
用 `EMBEDDING_CACHE_DIR` 指定缓存位置。

> 后端必须在**仓库根目录**启动：`main.py` 通过 `load_dotenv()` 读取 `.env`，
> 换目录运行会报 `DEEPSEEK_API_KEY 未配置`。

## 知识库：四个阶段

| 阶段 | 命令 | 产物 |
| --- | --- | --- |
| ① PDF → 文字 | `python -m backend.knowledge.export_chunks` | `data/exports/text/<document_id>.txt` |
| ② 文字 → 切片 | 同上（一条命令同时产出 ①②） | `data/exports/chunks.jsonl`、`data/exports/chunks-overview.md` |
| ③ 切片 → 向量 | `python -m backend.knowledge.build_index` | `data/chroma/`（collection `knowledge_chunks`） |
| ④ 检索 + 组装 prompt | 运行时自动发生 | —— |

两个脚本的分工：

- `build_index.py`：真正的入库程序。抽取 → 切块 → 向量化 → 写入 Chroma。
  为每份文档使用**显式 `document_id`**（而不是由绝对路径推导，避免换机器后写入两套记录）；
  幂等（重复运行不产生重复数据）；**不会删除任何已有数据**。
  加 `--dry-run` 可以只看切块结果而不写库。
- `export_chunks.py`：把 ①② 两个阶段的产物落成文件。**不加载向量模型、不碰向量库**，
  秒级完成，可用来看"PDF 到底被切成了什么"。

两者共用同一套 `load_pdf_text` / `chunk_text`，所以切片数量必然一致。

### 已提交的产物

为了让克隆后无需重建即可运行，以下产物纳入版本控制：

| 产物 | 内容 |
| --- | --- |
| `data/chroma/` | 向量库：75 条记录 / 10 份文档 |
| `data/exports/text/` | 每份文档的抽取文本 |
| `data/exports/chunks.jsonl` | 一行一个 chunk，含全文与全部元数据 |
| `data/exports/chunks-overview.md` | 可读索引（每块长度与首行） |

重建代价：`build_index` 约 10 秒，`export_chunks` 约 4 秒。向量库是二进制文件，
重新生成会产生整体 diff；若不希望它进版本库，把 `.gitignore` 里对应的说明注释改回
`data/chroma/` 与 `data/exports/` 两行即可。

## 元数据

检索按元数据过滤，每个 chunk 落库时带 7 个字段：

| 字段 | 来源 |
| --- | --- |
| `document_id` | 入库时指定（稳定键，检索过滤用它） |
| `source` | PDF 文件名 |
| `year` | 入库时指定（文档所属年度） |
| `major` | 入库时指定（`全校` 或具体学院） |
| `document_type` | 入库时指定（如 `竞赛列表`、`管理办法`） |
| `chunk_index` | 该文档内的位置序号（从 0 开始） |
| `chunk_hash` | 切片内容的 SHA-256 |

过滤只支持**等值**比较，且是"先过滤后取 top_k"。注意：**当前主流程并没有传过滤条件**
（见 [`OPEN_ISSUES.md`](OPEN_ISSUES.md) 的 P0-1），所以线上仍是全库检索。

## 接口

| 接口 | 说明 |
| --- | --- |
| `GET /api/hello` | 健康检查 |
| `POST /api/chat` | 请求体 `{"messages":[{"role":"user","content":"..."}]}`，返回 SSE 流：`data: {"content": "..."}`，以 `data: [DONE]` 结束 |

CORS 只放行 `http://localhost:5173` 与 `http://127.0.0.1:5173`。

## 测试

```bash
python -m unittest discover -s backend -t . -p "test_*.py"
```

当前 **154 个用例全部通过**（约 18 秒）。覆盖抽取、切块、向量化、存储、检索、
prompt 组装、入库幂等性、问题集自洽性与入库文档表的一致性。

## 验证工具（`tools/rag_verification/`）

三个脚本都**只读仓库、只写系统临时目录**，不会打开或修改 `data/chroma`：

| 脚本 | 用途 |
| --- | --- |
| `verify_rag.py` | E1–E10 全流程实验（真实模型 + 临时向量库） |
| `verify_inventory.py` | 校验 10 份 PDF 的来源清单（45 条原文断言 + 校验和） |
| `check_retrieval.py` | 用真实检索跑 `evaluation_dataset.json` 里的问题集，输出逐题核对记录 |

用法与结果解读见 `tools/rag_verification/README.md`。

## 已知问题

见 [`OPEN_ISSUES.md`](OPEN_ISSUES.md)。摘要：

1. ~~生产链路不传 `metadata_filter`~~ **已修复（仅限显式年份）**：问题写明「2026 年」时
   只检索 2026 年资料；未写年份时仍是全库检索。`major` 与适用范围仍不推断（P0-1）。
2. **关键条款可能取不到**（P0-2）：条款遗漏**依赖问法**——同一条"适用范围"条款
   在不同问法下排第 5 名或第 2 名；提高 `top_k` 未带来覆盖提升，只增加无关片段。
   见 [`RETRIEVAL_QUALITY.md`](RETRIEVAL_QUALITY.md)。
3. **没有可证明可靠的最低分阈值**（P0-3）：正负例分数区间相距仅 0.024。
   见 [`RETRIEVAL_QUALITY.md`](RETRIEVAL_QUALITY.md)。

## 尚未实现

- Agent 生成任务计划、用户确认、任务列表展示（`feat/agent`、`feat/task-ui-zyhh` 尚为空分支）
- 任务管理后端已开发但未合并（`feat/task-api`）
- 用户认证、对话历史

## 开发约定

- 一人一功能分支，不直接向 `main` 推送；完成后提交 PR 合并
- PR 需写明：修改内容、涉及文件、测试命令、实际测试结果、已知问题
- 修改公共接口、主流程或大规模重构前先与负责人确认
- 改代码前先读现有实现；测试失败或需要触碰约定范围外的文件时先沟通

## 文档索引

| 文件 | 内容 |
| --- | --- |
| `README.md` | 本文件：项目结构、启动、知识库流程 |
| `RAG_VERIFICATION.md` | RAG 验证报告：流程说明、实测数据、问题清单 |
| `OPEN_ISSUES.md` | 当前未解决的问题与待决策事项 |
| `RETRIEVAL_QUALITY.md` | 检索质量评估：`top_k` 对比与拒答阈值实验 |
| `PULL_REQUEST.md` | `feat/rag-verification` 的 PR 描述 |
| `tools/rag_verification/README.md` | 验证脚本的用法与结果解读 |
