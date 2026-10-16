# PR: 验证现有 RAG，并提升知识库可靠性

- 仓库：`https://github.com/kento-wts/DMU-AI-Learning-Assistant.git`
- 分支：`feat/rag-verification`
- 基线：`main` = `379b6e8 feat: make RAG ingestion idempotent`
- 分支顶端提交（以 `git log` 为准）：
  1. `feat(knowledge): verify retrieval and fix knowledge-base reliability defects`
     —— 代码与测试
  2. `docs: add the PR description for feat/rag-verification`
  3. `docs: correct the baseline note to the real repo history`
  4. `docs: record the re-verified run and fix the stale delivery note`
     —— 修正报告第 6 节的过期说明（原先误写"仓库无 remote"）、把
     `verify_rag.py` 的元数据样本改为 key-sorted 输出、补记本次复核结果
- 完整报告：[`RAG_VERIFICATION.md`](RAG_VERIFICATION.md)

## 这个 PR 做了什么

1. **只读验证**了现有 RAG 的真实流程与真实表现（真实 10 份 PDF + 真实
   `bge-small-zh-v1.5` 向量，全部写临时目录）。
2. **修复 3 个已确认的缺陷**，范围限制在 `backend/knowledge/`。
3. **补充 27 个可重复执行的测试**（87 → 114，全部通过）。
4. 交付**可核验的知识材料来源清单**（45 条原文断言 + 校验和自动校验）。
5. 把**未修复的问题与未验证的风险**全部列清楚，没有夸大结论。
6. **阶段二补充**：把带标准答案的问题集从 1 条扩到 **22 条**，
   新增逐题检索核对记录与问题集护栏测试（见下方专节）。

## 关键发现（都附复现方式）

### 1. 重复入库是安全的 ✅

75 chunks 重复入库两轮仍是 75，重复 ID 0，重复内容 0。
chunk ID 由 `sha256(document_id | chunk_index | sha256(chunk))` 决定，
`replace_document` 还会清理改短后的陈旧块。

```powershell
python tools/rag_verification/verify_rag.py   # E1、E2
```

### 2. 生产链路从不使用 `metadata_filter`，跨年份资料混检 ❌（未修复，需决策）

`backend/main.py` 调 `retrieve(query)`，不传 `metadata_filter`。实测：

| 问题 | 过滤 | 结果 |
| --- | --- | --- |
| `2026年大连海事大学本科生有哪些创新创业竞赛？` | 无 | top_3 = **2025 列表 + 2023 管理办法 + 2024 奖励办法**，2026 列表 **0 条** |
| 同上 | `year=2026` | 9 条，**全部**来自 2026 列表 |

这是当前对可靠性影响最大的问题。修复需要改动 `main.py`（超出本次边界），
且涉及产品决策，因此**没有擅自修改**。

```powershell
python tools/rag_verification/verify_rag.py   # E5、E7
```

### 3. 2026 竞赛列表 PDF 用"康熙部首"抽取，向量畸变 ❌→✅ 已修复

`附件1.《…竞赛列表(2026年)》.pdf` 抽出的“大”是 `U+2F24`（KANGXI RADICAL BIG）
而不是 `U+5927`，共 **37 个字符、631 处**。后果：

- 4 个人工标注的竞赛名在原始抽取文本里**一个都不存在**，NFKC 归一化后**全部出现**；
- 入库 chunk 与用户查询处于不同向量空间
  （`cosine(修复前向量, 修复后同义向量) = 0.885`）；
- 该文档 9 个 chunk 中 8 个分数上升，最大 **+0.0435**（E10）。

**诚实说明**：修复前/后 top_k 命中数**没有变化**（E9：0/4、3/4、3/4 完全相同），
因为这个 chunk 本来就在第 5 名，+0.0435 不足以挤进前 3。
所以这修的是一处**确定的向量畸变**，**不是**准确率提升，报告里没有那样写。

修复：`pdf_loader` 每页文本 NFKC + `embedding.normalize_for_embedding`
对索引侧和查询侧同时归一化（双保险）。

### 4. RAG prompt 完全丢失文档来源 ❌→✅ 已修复

修复前 `build_rag_prompt` 只写 `result.text`，metadata 全部丢弃 →
模型无法给出处、无法区分 2025/2026、看不到"适用于 2022 级及以后"这类范围限定。

修复后 prompt：

```
[资料 1] (来源文件: …推免…的通知.pdf；文档类型: 推免办法；适用年份: 2025；文档标识: dlmu-postgraduate-recommendation-2025)
```

无 metadata 时输出与旧版**完全一致**（有测试守护）。

### 5. `ingest_pdf_to_store` 忽略 `max_chars` ❌→✅ 已修复

`ingest_pdf(path, max_chars)` 支持自定义上限，但真正落库的函数写死了
`chunk_text(...)`。已改为可选参数 `max_chars=DEFAULT_MAX_CHARS`（默认值不变，向后兼容）。

## 未修复的问题（明确留给负责人）

| 编号 | 问题 | 为什么没动 |
| --- | --- | --- |
| O1 | `metadata_filter` 未接入主流程（见上） | 需改 `main.py` + 产品决策（过滤方式、空结果降级策略） |
| O2 | 中队级测评细则（仅 2025 级 2 中队）全库可检索 | 属 O1 的元数据过滤范畴 |
| O3 | 请假单（表单，非制度文件）入库 | 建议单独定 `document_type` 并默认排除 |
| L1 | 竞赛列表按列分离抽取，chunk 丢失行归属 | 需表格/版面解析，属"重写 RAG"范畴 |
| L2 | 评估集只有 **1 条** query | 建议扩到 ≥20 条 |
| L3 | 空结果与低分结果不可区分（无阈值，分数 clamp 到 0） | 加阈值会改变线上回答行为，需先定策略 |
| L4 | 仓库不记录文档来源信息 | 本次已补来源清单+自动校验；建议纳入入库 metadata |

## 兼容性与行为变化

- `embed_text` / `load_pdf_text` / `build_rag_prompt` **签名均未变**。
- 行为变化 1：入库与查询文本会做 NFKC 归一化。全角 `（）` → `()`，
  `U+00A0` → 普通空格。对普通中英文无影响。
- 行为变化 2：metadata 含 `source` 时资料头多一个括号标注。
  唯一依赖旧精确前缀的既有测试已按新语义更新，并新增测试锁定"无 metadata = 旧格式"。
- `ingest_pdf_to_store` **新增可选参数**，旧调用点无需改动。
- 未改动任何公共返回结构、异常类型、`SearchResult` / `VectorRecord` 定义。
- **未删除任何向量库、未重新生成全量 Embedding。**
  仓库中本来也不存在 `data/chroma/`（被 `.gitignore` 忽略）。
  P1/P2 要正式生效需重新入库，步骤写在报告 3.2 节，**等确认后再执行**。

## 测试

```powershell
python -m unittest discover -s backend -t . -p "test_*.py"
# 修复前：Ran 87 tests ... OK
# 修复后：Ran 114 tests ... OK
```

新增用例：

| 文件 | 新增 | 覆盖 |
| --- | --- | --- |
| `test_knowledge_documents.py`（新文件） | 8 | 语料级护栏：校验和快照、无兼容字符残留、无超长/空 chunk、秒级完成 |
| `test_pdf_loader.py` | 4 | 康熙部首归一化、`U+00A0` 归一化 |
| `test_embedding.py` | 8 | 索引侧与查询侧送入模型完全一致 |
| `test_prompt_builder.py` | 7 | 来源进入 prompt、内部字段不泄漏、无资料禁止编造 |
| `test_ingest_pipeline.py` | 3 | `max_chars` 生效、纯空白文档、落库无兼容字符 |

验证脚本（只读仓库，只写临时目录）：

```powershell
python tools/rag_verification/dump_pdf_meta.py
python tools/rag_verification/verify_inventory.py   # 45 条断言 PASS
python tools/rag_verification/verify_rag.py         # E1–E10
```

### 推送前的复核（2026-10-16，本机重跑）

| 命令 | 实际结果 |
| --- | --- |
| `python -m unittest discover -s backend -t . -p "test_*.py"` | `Ran 114 tests in 13.524s ... OK`，进程退出码 **0**（可直接作 CI 门禁） |
| `python tools/rag_verification/verify_inventory.py` | `documents checked: 10   text claims verified: 45`，`PASS` |
| `python tools/rag_verification/verify_rag.py` | E1 共 75 chunks、每份文档 `compatibility_chars = 0`；E2 `duplicate ids = 0`、`PASS`；E5 无过滤时 top_3 = 2025 列表 + 2023 办法 + 2024 奖励，`year=2026` 时 9 条全部来自 2026 列表；E7 `year=1999` 返回 0 条、`top_k=50` 命中单文档时返回 1 条；E10 9 个 chunk 中 8 个分数上升 |

以上数字与报告 2.3 节一致。说明两点：

1. 报告开头的 `repository root` 与临时 Chroma 目录是运行机器的绝对路径，
   换机器必然不同，不属于有效差异（已写进 `tools/rag_verification/README.md`）。
2. E8 的 metadata 样本原本随词典顺序变化，现已改为 `sort_keys` 输出；
   连续两次运行在去掉上述两行后**逐行一致**。

## 阶段二补充：带标准答案的问题集与核对记录

| 交付物 | 内容 |
| --- | --- |
| `backend/knowledge/evaluation_dataset.json` | 问题集从 1 条扩到 **22 条**：16 条有期望文档、4 条语料缺口（`not_in_corpus`）、1 条抽取不可靠案例、1 条适用范围陷阱；原 `q1` 未改动。新增字段 `expected_behaviour` / `expected_document_ids` / `ground_truth_points` |
| `tools/rag_verification/check_retrieval.py` | 用真实向量模型跑全部问题，输出逐题记录：分数、`document_id`、来源文件、命中的标准答案要点，以及留白的人工核对栏。只写临时 Chroma，不打开 `data/chroma` |
| `tools/rag_verification/reference/retrieval-check-record.txt` | 核对记录存档 |
| `backend/knowledge/test_evaluation_dataset.py` | 8 个护栏用例：id 唯一、可答题必须有期望文档与标准答案、负样本不得指向文档、期望文档必须在来源清单里存在 |

实测（`top_k=5`，真实 `bge-small-zh-v1.5`）：

| 指标 | 结果 |
| --- | --- |
| 期望文档进入 top_3 | **16 / 16** |
| 语料缺口题的最高分 | `q18`「转专业」**0.7379**、`q19` 0.6590、`q20` 0.6346、`q21` 0.6375 |
| 跨年份混检 | `q15` 的 #1 是 **2025 列表**，2026 列表到 #2 才出现；`q17` 的 #1 也是 2025 列表 |
| 范围陷阱 | `q22` 的 #1 是**仅适用信息学院 2025-2 中队**的测评细则 |

**诚实说明**：16/16 **不是准确率**。标准答案是人工摘录的、只覆盖部分要点；
22 条里没有一条经过"回答是否正确"的判定；出题人与读文档的是同一人。
真正值得注意的是负样本——语料里根本没有"转专业"，却仍返回 0.7379 分的 chunk，
**比多道可答题的 #1 还高**，这正是 L3（无最低分阈值）的量化证据。

测试数 **114 → 122**（新增 8 个问题集护栏用例），全部通过。

## 知识材料来源

10 份 PDF 的文号、发布/施行日期、适用范围已逐份从原文抽取并记录在
`tools/rag_verification/document-inventory.json`，由 `verify_inventory.py`
自动校验（sha256、页数、`/CreationDate`、抽取字符数、45 条原文断言）。

标注为过期/无法核实的材料：

- **2025 竞赛列表**：对 2026 年问题属历史资料（已标记，未删除）。
- **学籍管理规定（2021）**：发布时间较久，仓库内无法核实是否有新版 → 标为"未核实"。
- **2026 竞赛列表**：文档本身**无发文机关署名、无文号** → 记为 `null` 并注明原因，
  **没有编造发文单位**。
- **中队测评细则**：无文号无发布日期，`year=2025` 是归类而非发布日期。
- **请假单**：无日期，属表单模板。

未执行任何"编造内容"的操作；所有日期与文号均可由
`python tools/rag_verification/verify_inventory.py` 复现核验。

## 尚未验证的风险（详见报告第 5 节）

1. **跨年份误答**（O1 未修复）——最高优先。
2. `replace_document` 的 upsert/delete **非原子**，中途失败会残留旧块，无测试无告警。
3. `document_id` 默认依赖**绝对路径**：换目录/换机器会写入两套记录；跨平台大小写行为不一致。
4. 表格类文档列错位对回答质量的影响未量化。
5. **未调用真实 DeepSeek API**——本 PR 所有结论止于"检索返回什么、prompt 里有什么"，
   回答是否更准确**未验证**。
6. NFKC 修复只覆盖会被 NFKC 改写的兼容字符区间；其他乱码形式（CID 映射错误、
   缺字 `U+FFFD`）检测不到。
7. 并发写同一文档、模型返回空向量等分支未实测。

## Review 时请重点确认

1. **O1 的选型**：前端传参 / 规则抽取年份 / 其他？确定后我另开分支实现（含降级策略）。
2. **P1 的归一化位置**是否认可（`pdf_loader` 修存储文本 + `embedding` 双侧归一化）。
3. **重新入库的执行时机**（报告 3.2 节流程）。
4. 报告 2.3 节对 E4/E9 的诚实说明是否清晰——**没有任何"整体准确率"结论**。

## 关于基线的说明

最初的一轮检查是在一份 zip 导出上做的，当时误以为仓库没有 git 历史。
之后确认该 zip 是 `379b6e8` 的完整导出：`backend/`、`frontend/`、`README.md`、
`.gitignore` 以及 10 份 PDF 的 blob 哈希**与 `379b6e8` 逐字节相同**。

因此本分支已从 `379b6e8` 重新建立，改动以 cherry-pick 方式落到真实历史上，
下面所有实测数字都取自与真实仓库一致的代码。
