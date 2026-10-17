# RAG 验证报告与知识库可靠性改进

- 仓库：`https://github.com/kento-wts/DMU-AI-Learning-Assistant.git`
- 分支：`feat/rag-verification`（基于 `main` = `379b6e8 feat: make RAG ingestion idempotent`）
- 验证日期：2026-10-16
- 运行环境：Python 3.13.12 (Windows)，chromadb 1.5.9，fastembed 0.9.0，pypdf 6.20.1，
  嵌入模型 `BAAI/bge-small-zh-v1.5`（512 维，本地运行，无 API Key）
- 范围：`backend/knowledge/` 及相关测试与文档。未改动 Agent 主流程、`backend/main.py`、
  `backend/rag_chat.py` 与前端。

> 验证过程的说明：最初的检查是在一份 zip 导出上做的，当时误以为仓库没有 git 历史。
> 之后确认该 zip 是 `379b6e8` 的完整导出——`backend/`、`frontend/`、`README.md`、
> `.gitignore` 以及 10 份 PDF 的 blob 哈希**与 `379b6e8` 逐字节相同**。
> 因此本分支的改动已重新变基到真实 `main`（`379b6e8`）之上，
> 下面所有实测数字都是在与真实仓库一致的代码上得到的。

---

## 1. RAG 实际流程

### 1.1 文档如何进入知识库

目前**只有一条入 库路径**，而且是**手动、单文件**执行的：

```
python -m backend.knowledge.ingest_document <pdf 路径> \
    --year <年份> --major <专业> --document-type <文档类型> [--document-id <稳定 ID>]
```

`ingest_document()` 的职责分工：

| 环节 | 代码位置 | 行为 |
| --- | --- | --- |
| 抽取文本 | `pdf_loader.load_pdf_text` | `pypdf.PdfReader` 逐页 `extract_text()`；空白页丢弃；非空页用空行拼接；每页做 NFKC 归一化 |
| 分块 | `chunker.chunk_text` | 先按空行切段；短段尽量合并；超长段按句读边界切；单句超长才硬切。默认上限 1200 字符 |
| 向量化 | `embedding.embed_text` | fastembed 本地 `BAAI/bge-small-zh-v1.5`，逐块串行调用；空文本返回 `[]` |
| 元数据组装 | `ingest.ingest_pdf_to_store` | 合并调用方 metadata + `document_id` + `source`（文件名）+ `chunk_index` + `chunk_hash` |
| 写入 | `chroma_store.ChromaVectorStore.replace_document` | 先 `upsert_many` 新块，再删除同 `document_id` 下的陈旧 ID |

**关键点**

1. **没有任何自动扫描**。把 PDF 放进 `backend/knowledge/documents/` 不会触发任何处理，
   也不会自动入库。**阶段三起仓库内自带一份已构建好的向量库**
   （`data/chroma/`，75 条 / 10 份文档，已纳入版本控制），克隆后可直接检索；
   但新增文档仍需手工执行导入命令。
2. **metadata 由调用方手写**。`--year` / `--major` / `--document-type` 是必填的，
   代码里没有校验；10 份文档的元数据集中写在 `build_index.py` 的文档表里，
   来源信息的可核验清单则在 `tools/rag_verification/document-inventory.json`。
   同一个 `year` 是"文档所属年份"还是"发布年份"仍取决于填写者。
3. **`document_id` 默认是归一化后的绝对路径**（`os.path.normcase(Path.resolve())`）。
   因此把 `backend/knowledge/documents/` 换一个目录、或换一台机器，同一个 PDF 会被当成
   **两个不同文档**写入两套 chunk。
4. 本次验证使用了 10 份文档的显式 `document_id`（见第 4 节），以保证跨机器可复现。

### 1.2 分块、Embedding、向量存储与检索的完整链路

```
PDF ──pypdf──► 每页文本 ──NFKC──► 全文
                                   │
                            chunk_text(max_chars=1200)
                                   │
              ┌──────── 每个 chunk ────────┐
              │  embed_text(chunk)         │  fastembed / bge-small-zh-v1.5（512 维）
              │  id = sha256(document_id ｜ chunk_index ｜ sha256(chunk)) │
              └────────────┬───────────────┘
                           ▼
        ChromaVectorStore.replace_document(document_id, records)
             upsert_many(新块) → delete(旧 document_id 中不在新集合里的 ID)

查询路径：
用户问题 ──► Retriever.retrieve(query, top_k=3, metadata_filter=None)
                │  embed_text(query)
                ▼
        ChromaVectorStore.search(query_vector, top_k, metadata_filter)
                │  collection.query(n_results=min(top_k, collection.count()),
                │                   where=_build_where(filter),
                │                   include=["documents","metadatas","distances"])
                │  score = clamp(1 - cosine_distance, 0, 1)
                ▼
        list[SearchResult(text, score, metadata)]
                │
                ▼
        prompt_builder.build_rag_prompt(query, results) ──► DeepSeek 消息
```

`SearchResult` 是 `chroma_store` 与 `vector_store` 共用的返回类型，
`Retriever` 通过 `TYPE_CHECKING` 依赖 `ChromaVectorStore`，但实际只用它的 `search()`，
所以测试里可以注入任意满足 `search()` 签名的替身。

**实际调用点**：`backend/main.py::chat()` 调用
`_get_retriever().retrieve(latest_user.content)`，**不传 `top_k`、不传 `metadata_filter`**。

### 1.3 元数据如何保存和过滤

每一条 chunk 的 metadata 固定包含：

| 字段 | 来源 | 示例 |
| --- | --- | --- |
| `document_id` | 调用方指定，或归一化绝对路径 | `dlmu-competition-list-2026` |
| `source` | `Path(pdf_path).name`（会被覆盖，调用方传的同名值无效） | `附件1.《…(2026年)》.pdf` |
| `year` | 调用方 `--year` | `2026` |
| `major` | 调用方 `--major` | `软件工程` |
| `document_type` | 调用方 `--document-type` | `竞赛列表` |
| `chunk_index` | 由 ingest 生成 | `2` |
| `chunk_hash` | `sha256(chunk 文本)` | 64 位十六进制 |

**过滤机制**

- `_build_where()` 把等值字典翻译成 Chroma 的 `where` 语法：单条 → `{key: {"$eq": v}}`，
  多条 → `{"$and": [...]}`。只支持**等值**，不支持范围比较、`$in`、`$ne`。
- **过滤是"先过滤后取 top_k"**，不是"取 top_k 再过滤"，所以过滤后结果条数可能少于 `top_k`，
  甚至为 0。`_build_where(None)` 返回 `None`，Chroma 视为不过滤。
- `search()` 用 `n_results=min(top_k, collection.count())`，因此在整库上按 `top_k` 限制，
  在过滤子集上则由 Chroma 内部处理。实测 `top_k=50` + 只命中 1 个文档时返回 1 条，没有报错。

**结论：元数据被完整保存，但生产链路完全没有使用过滤能力。**
`backend/main.py` 与 `backend/rag_chat.py` 都允许传 `metadata_filter`，
但 `main.py` 的 HTTP 层没有任何地方从前端请求里解析出 `year` / `major` / `document_type`，
所以**线上永远是全库检索**。

### 1.4 检索结果是否保留文档来源

**保留，而且信息足够。**

- `ChromaVectorStore.search()` 主动 `include=["documents","metadatas","distances"]`，
  并把 `metadata` 原样放进 `SearchResult`。实测返回的 metadata 含全部 6 个字段
  （`document_id`/`source`/`year`/`document_type`/`chunk_index`/`chunk_hash`）。
- **但修复前 `build_rag_prompt` 只把 `result.text` 写进 prompt，完全丢弃 metadata**，
  因此 LLM 拿不到"这段话出自哪份文件、哪一年"，无法给出处，也无法识别过期资料。
  （修复前的实测证据：prompt 中 `source` 文件名出现过 `False`。见第 6 节 P3。）

**修复后**：prompt 的每个资料块会带上可用的来源字段，例如

```
[资料 1] (来源文件: …推免…的通知.pdf；文档类型: 推免办法；适用年份: 2025；文档标识: dlmu-postgraduate-recommendation-2025)
```

### 1.5 重复运行入库是否产生重复数据

**不产生重复。** 这是本仓库做得最扎实的一块，代码与实测双向确认。

1. **chunk ID 由内容决定**：`sha256(f"{document_id}\0{chunk_index}\0{chunk_hash}")`。
   同一份 PDF、同一份 metadata 重复入库，ID 完全相同 → Chroma `upsert` 覆盖，不新增。
2. **`replace_document` 会清理陈旧块**：先 upsert 新版本，再删除 `existing_ids - new_ids`。
   因此文档改短（块数变少）时旧块会被删掉。
3. **不同文档的相同文本不会互相覆盖**：ID 里含 `document_id`，两份内容相同的 PDF
   只要 `document_id` 不同就是两套独立记录。
4. **同一文档内的重复段落不会被合并**：`chunk_index` 不同 → ID 不同 → 两条都留存。

实测（E1/E2，真实模型，临时 Chroma 目录）：

```
E1  10 份 PDF → 75 chunks，10 个不同 document_id，chunk 长度上限 1195 ≤ 1200
E2  第 1 轮 75 chunks，len(store)=75
    第 2 轮 75 chunks，len(store)=75
    重复记录 ID = 0，重复 (document_id, chunk_hash) 对 = 0   → PASS
```

**已知的非原子性风险（不是重复，但会造成残留）**：
`replace_document` 的 upsert 与 delete 之间没有事务。如果 upsert 成功、delete 失败
（进程被杀、磁盘错误），旧块会残留在库里，同一 `document_id` 下同时存在新旧内容。
`chroma_store.py` 的 docstring 已经声明了这一点。目前没有测试覆盖该路径。

### 1.6 当前已有的测试与评估方法

**测试（unittest，共 87 个用例，修复前基线）**

| 文件 | 覆盖内容 |
| --- | --- |
| `test_chunker.py` | 空文本、短段合并、句读切分、英文空格、无标点兜底、`max_chars` 校验 |
| `test_pdf_loader.py` | 缺失文件、非法 PDF、多页抽取 |
| `test_embedding.py` | 空文本、类型校验、假模型接口、异常包装、余弦相似度数学性质、**真实中文语义相近性对比** |
| `test_vector_store.py` | 内存库：增删查、`top_k`、维度一致性、元数据先过滤、排序 |
| `test_chroma_store.py` | 持久化库：写入/检索/持久化、`upsert` 去重、`replace_document` 清理陈旧块、`delete_by_document_id` 隔离 |
| `test_retriever.py` | 参数校验、`top_k`、`metadata_filter` 透传（用 FakeStore） |
| `test_prompt_builder.py` | 资料编号、顺序保持、空结果提示、参数校验 |
| `test_ingest.py` | `ingest_pdf` 抽取+分块、无文本 PDF、缺失文件 |
| `test_ingest_document.py` | CLI 包装层委派、幂等入库、metadata 落库 |
| `test_ingest_pipeline.py` | 端到端：真实 Chroma + mock 向量；幂等、同名不同目录、文档改短、空文档清空、解析失败保留旧数据、不误伤其他文档 |
| `backend/test_main.py` / `test_rag_chat.py` | 只覆盖 `metadata_filter` 的**透传**，这掩盖了 1.3 节的"生产链路不传过滤条件"问题 |

**评估（`evaluate_retrieval.py` + `evaluation_dataset.json`）**

- 只有 **1 条** query（`q1`，"软件工程专业大二学生想参加学院承办的 A 类竞赛"），
  人工标注 4 个候选竞赛名。
- 脚本**明确声明不算 recall**，只打印各 `top_k`（3/5/10）的完整 chunk、分数、metadata、
  以及一个"名称重叠"审查辅助项。
- 依赖真实 Chroma 库；库为空时只会打印 `Collection size: 0` 并返回 0，**不会报错、
  也不会提示"知识库为空所以结论无意义"**。
- `test_retrieval_real.py` 是同类的调试脚本（固定 query + `top_k=3`），也是直接读默认库。

**评估方法的局限**：本报告第 1 版只有 1 条 query、4 个标注、没有 negative 样本，
也没有跨年份的区分性用例。**该局限已在阶段二补充**：问题集扩到 24 条
（18 条有期望文档、4 条真语料缺口、1 条抽取不可靠、1 条范围陷阱），
并有逐题核对记录，见 2.5 节。
即便如此它仍是一个抽查样本而**不是基准**，不得据此外推准确率。

### 1.7 发现的问题、复现方法与修复建议

约定：**P = 已修复**，**O = 待负责人决策**，**L = 已知局限（本次未处理）**。

#### P1（高）2026 竞赛列表 PDF 以"康熙部首"兼容字符抽取，导致向量畸变

- **现象**：`附件1.《大连海事大学本科生创新创业竞赛列表(2026年)》.pdf` 抽取出的文本里，
  `大` 是 `U+2F24`（KANGXI RADICAL BIG）而不是 `U+5927`，共 **37 个不同字符、631 处**。
  实测 4 个人工标注的竞赛名在原始抽取文本中**一个都不存在**，经 NFKC 归一化后 4 个全部出现。
- **后果**：入库的 chunk 与用户正常输入的查询处于不同的向量空间。实测
  `cosine(修复前"中国⾼校计算机⼤赛"向量, 修复后"中国高校计算机大赛"向量) = 0.885282`；
  对同一 query，2026 列表各 chunk 的相似度被系统性压低（见下方 E10）。
- **复现**：
  ```
  python tools/rag_verification/verify_rag.py     # 见 E3 与 E10 段
  ```
  E10 结果（query：`中国大学生计算机设计大赛是什么级别的竞赛？`）：

  | chunk | 修复前 cos | 修复后 cos | 差值 | 含部首字数 |
  | --- | --- | --- | --- | --- |
  | 2 | 0.666180 | 0.709721 | **+0.043542** | 43 |
  | 5 | 0.581974 | 0.618172 | +0.036198 | 42 |
  | 3 | 0.638712 | 0.665318 | +0.026606 | 73 |
  | 4 | 0.594650 | 0.618242 | +0.023592 | 93 |
  | 0 | 0.612652 | 0.626446 | +0.013795 | 99 |
  | 1 | 0.612755 | 0.609375 | −0.003380 | 92 |

  9 个 chunk 中 8 个分数上升，最大 +0.0435，1 个轻微下降 −0.0034。
- **修复**：在 `pdf_loader._normalize_page_text` 中对每页文本做 NFKC；
  在 `embedding.normalize_for_embedding` 中对**所有**送入模型的文本做 NFKC
  （双保险：即使将来换了别的加载器，索引侧与查询侧仍然一致）。
- **顺手修掉的同源问题**：NFKC 同时把全角 `（）：,` 与不换行空格 `U+00A0` 规范化，
  可读性与检索一致性都变好。

#### P2（中）`ingest_pdf_to_store` 忽略分块上限，与 `ingest_pdf` 行为不一致

- **现象**：`ingest_pdf(pdf_path, max_chars)` 支持自定义上限，但真正落库的
  `ingest_pdf_to_store` 内部写死 `chunk_text(extracted_text)`，**不接受也不传递 `max_chars`**。
  调用方以为限制生效，实际按默认 1200 切。
- **复现**：修复前调用 `ingest_pdf_to_store(path, {}, store)` 后再用 `max_chars=100` 调
  `ingest_pdf`，两者块数与块长不同。现在由
  `test_ingest_pipeline.test_max_chars_is_honoured_when_storing_chunks` 守护。
- **修复**：给 `ingest_pdf_to_store` 增加**可选**参数 `max_chars=DEFAULT_MAX_CHARS`
  并传递给 `chunk_text`。默认值不变，向后兼容。

#### P3（高）RAG prompt 不携带文档来源与年份

- **现象**：`build_rag_prompt` 只输出 `[资料 N]\n{chunk.text}`，metadata 被丢弃。
  实测修复前 `source 文件名是否出现在 prompt = False`。
- **后果**：(a) 无法要求模型给出处；(b) 模型无法区分 2025 与 2026 竞赛列表，
  也看不到 `适用于2022级及以后年级` 这类只写在某一条里的范围限定；
  (c) `main.py` 的 `RAG_CONTEXT_NOTE` 只防"资料里的指令"，不防"用过期资料回答"。
- **复现**：`python tools/rag_verification/verify_rag.py` 的 E8 段；
  修复后 `来源文件` / `适用年份` 均出现在 prompt 中，且 `chunk_hash` 等内部字段不泄漏。
- **修复**：`prompt_builder` 从 `SearchResult.metadata` 读取 `source` / `document_type` /
  `year` / `document_id` 渲染成 `[资料 N] (来源文件: …；适用年份: …)`；
  缺字段或空字符串则整段省略（无 metadata 时输出与旧版完全一致）；
  并在指令中要求"说明出处、注意适用年份与适用范围、无资料时不要编造"。

#### O1（高，需决策）生产链路从不使用 `metadata_filter`，年份/专业/适用范围不生效

- **现象**：`backend/main.py::chat()` → `_get_retriever().retrieve(latest_user.content)`，
  没有 `metadata_filter`。实测：问 `2026年大连海事大学本科生有哪些创新创业竞赛？`
  时，`top_k=3` 返回的是 **2025 列表 + 2023 管理办法 + 2024 奖励办法**，
  **2026 列表一条都没有**；`top_k=10` 才有 3 条来自 2025 列表。加上
  `metadata_filter={"year": 2026}` 后稳定返回 9 条全部来自 2026 列表。
- **影响**：这是当前对"知识库可靠性"影响最大的一个问题——metadata 已具备，
  但模型可能拿着 2025 年名单回答 2026 年的问题；1.4/P3 修好之后，
  模型至少能看到年份标签，但候选集仍然混着旧文档。
- **复现**：`python tools/rag_verification/verify_rag.py` 的 E5、E7 段。
- **建议（本次未改，因为超出 `backend/knowledge/` 范围且会改变主流程行为）**：
  1. 在 `ChatRequest` 上增加可选的 `year` / `major` / `document_type` 字段，
     由前端显式提供，`main.py` 组装成 `metadata_filter` 传入 `retrieve()`；
  2. 或者由 `main.py` 用简单规则从问题中抽取"20XX 年"再过滤；
  3. 无论选哪种，都建议先做"过滤后为空则回退到不过滤并在回答中说明"的降级策略。
  评审时请明确选型，我再单独开一个改动范围清楚的分支。

#### O2（中）`2025-2中队本科生综合素质测评实施细则` 的适用范围极窄，但全库可检索

- 该文件仅适用于**信息科学技术学院 2025 级 2 中队**（第三条、第二十四条），
  既无文号也无发布日期，落库时 `year=2025` 是"文档所属年份"而非发布日期。
- 实测在"软件工程专业大二学生能参加哪些 A 类竞赛"这种问题上，它会作为第 4 名返回
  与竞赛无关的评奖评优条款。
- **建议**：不要删文件，而是把适用范围写进 metadata（例如
  `applicable_scope` / `cohort`）并在前端按专业/年级过滤。属于 O1 的同一类问题。

#### O3（中）`大连海事大学学生离校请假单.pdf` 是表单而非制度文件

- 抽取结果 42 行、含大量空字段、无日期，仅产出 1 个 398 字符的 chunk，
  信息密度极低；`year=2025` 纯属调用方假设。
- **建议**：要么从知识库移除（不删除仓库文件），要么给它一个独立的
  `document_type=表单` 并让检索侧默认排除，避免它出现在程序性问题里。

#### L1（已知局限）竞赛列表是**按列分离**抽取的，chunk 内会丢失行归属

- 2025/2026 两份列表都以表格形式排版，`pypdf` 抽出的是"先所有序号、再所有名称、
  再所有主办单位…"的列式文本，而不是逐行。实测 chunk 中会出现
  `20|ACM-ICPC|国际大学生程序|设计竞赛|美国计算机学会|A|信息科学技术|学院|曹志英|18840915361|21|中国高校计算机大赛-大…`
  这种把两行的单元格混在一起的情况。
- **影响**：无法保证"某个竞赛 ↔ 它的类别/承办单位"在同一 chunk 内；
  问"A 类里有哪些信息学院的竞赛"时，证据是碎的。
- **未修复原因**：正确做法需要引入版面/表格解析（pdfplumber、camelot 等）或
  针对该列表的专用行重建逻辑，属于"重写 RAG"的范畴，超出本次边界。
- **已做的缓解**：`_normalize_page_text` 的 NFKC 让列内容的字符正确，
  至少名称本身可以被检索到。建议作为下一个独立任务评估。

#### L2（已缓解，但仍不是基准）评估集的问题覆盖面

- 第 1 版只有 1 条 query，无法支撑任何"准确率"结论。**阶段二已扩到 24 条**
  （18 条有期望文档、4 条真语料缺口、1 条抽取不可靠、1 条范围陷阱），
  阶段三又修正了两处错误标注并补入两条真负样本；逐题核对记录见 2.5 节。
- **仍然存在**：标准答案是人工从原文摘录的、只覆盖部分要点；
  24 条里 18 条已验证"期望文档进入 top_3"，但**没有**任何一条经过"回答是否正确"的判定。
- **建议**：下一步是人工逐条核对返回的 chunk（记录里已留核对栏），
  再决定是否需要更多题型（比较类、多文档综合类）。
  本报告**没有**给出整体准确率，只给出可复现的实验数字。

#### L3（已知局限）空结果与低分结果无法区分

- `_distance_to_score` 是 `clamp(1 - cosine_distance, 0, 1)`。余弦距离 ∈ [0,2]，
  距离 > 1（即负相关）时会被 clamp 到 0，**分数 0 与"稍微负相关"不可区分**；
  另外检索永远返回 `min(top_k, 命中数)` 条，没有最低分数阈值，
  所以"知识库没有相关资料"与"有 3 条弱相关资料"从 `Retriever` 层看不出区别
  （只有库为空时才返回 `[]`）。
- **未修复原因**：加阈值会改变线上回答行为（可能从"勉强回答"变成"拒答"），
  需要先定阈值策略并由负责人确认。
- **建议**：加一个可选 `min_score` 参数（默认 `None` 保持现状），
  并在 prompt 侧区分"无资料"与"弱相关资料"。

#### L4（已知局限）仓库不记录文档来源信息

- 10 份 PDF 的文号、发布日期、发文机关、适用范围都只写在 PDF 正文里，
  仓库既没有来源登记表，也没有落进向量库 metadata。
- **本次已补**：`tools/rag_verification/document-inventory.json` 记录了可核验的来源信息，
  并有 `verify_inventory.py` 对 45 条文本断言做自动化校验（防止文档被悄悄替换）。
- **建议**：把 `issue_date` / `issuing_body` / `applicable_scope` 也纳入入库 metadata。

---

## 2. 测试清单、命令与真实结果

### 2.1 环境准备（当前机器实测）

```powershell
# Python 3.13.12；chromadb / fastembed / numpy / uvicorn / pydantic 已存在
python -m pip install "pypdf>=6.0,<7.0" fastapi openai
```

首次运行会下载 `BAAI/bge-small-zh-v1.5`（本机已在缓存中，加载耗时约 1.2 s）。
如需指定缓存目录，可设置 `EMBEDDING_CACHE_DIR` 或 `EMBEDDING_MODEL`。

### 2.2 单元测试

```powershell
cd <repo root>
python -m unittest discover -s backend -t . -p "test_*.py"
```

| 阶段 | 命令 | 结果 |
| --- | --- | --- |
| 阶段一 · 修复前基线 | 同上 | `Ran 87 tests ... OK` |
| 阶段一 · 修复后（含新增 27 个用例） | 同上 | `Ran 114 tests in 18.775s ... OK` |
| 阶段二 · 加入问题集护栏 | 同上 | `Ran 122 tests ... OK` |
| **阶段三 · 当前** | 同上 | **`Ran 128 tests in 16.723s ... OK`，退出码 0** |

注：`pypdf` 会对 `test_pdf_loader` / `test_ingest` 里故意构造的非法 PDF 打印
`invalid pdf header` / `EOF marker not found` 到 stderr，这是被测代码的预期分支，不是失败。

新增/扩展的用例：

| 文件 | 新增用例 | 目的 |
| --- | --- | --- |
| `test_knowledge_documents.py`（**新增文件，8 个用例**） | 文档集与校验和快照一致、内容未被改动、每份文档可抽取、无兼容字符残留、竞赛列表含自身年份、无超长 chunk、无空 chunk | 语料级回归护栏，不需要向量模型，秒级完成 |
| `test_pdf_loader.py` (+4) | 康熙部首被归一化、抽取结果含规范检索词、`U+00A0` 归一化、普通文本不受影响 | P1 |
| `test_embedding.py` (+8) | `normalize_for_embedding` 单元性质、**"残缺文本与规范文本送入模型完全一致"** | P1 |
| `test_prompt_builder.py` (+7) | 来源/类型/年份/ID 进入 prompt、内部字段不泄漏、空 metadata 省略、新旧文档可区分、无资料时禁止编造 | P3 |
| `test_ingest_pipeline.py` (+3) | `max_chars` 落库生效、纯空白文档不产生块、**落库 chunk 无兼容字符** | P2 / P1 |

### 2.3 真实语料 + 真实向量的验证脚本

```powershell
python tools/rag_verification/dump_pdf_meta.py     # 只读：抽取文本与 PDF 元数据
python tools/rag_verification/verify_rag.py        # 全流程实验，写临时 Chroma 目录
python tools/rag_verification/verify_inventory.py  # 校验来源清单的 45 条文本断言
```

三个脚本**只读仓库、只写系统临时目录**（`tempfile.TemporaryDirectory`，且
`ignore_cleanup_errors=True`，因为 Windows 下 Chroma 会占住 sqlite 句柄），
**绝不打开或修改仓库内的 `data/chroma`**。

真实结果（完整输出见 `tools/rag_verification/reference/baseline-verification-report.txt`）：

| 实验 | 结论 |
| --- | --- |
| E1 真实入库 10 份 PDF | 75 chunks，10 个 document_id，最大 chunk 1195 字符，兼容字符残留 **0** |
| E2 全库重复入库两轮 | 75 → 75，重复 ID 0，重复 (document_id, chunk_hash) 0，**PASS** |
| E3 康熙部首损伤 | 631 处、37 个字符；4 个人工标注竞赛名在原始抽取中 0 个存在、NFKC 后 4 个全部存在 |
| E4 评估集 query（top_3/5/10） | 命中人工标注 **0/4、3/4、3/4**（仅名称重叠审查，非 recall） |
| E5 年份限定 query | 不带过滤：top_3 命中 2025 列表 + 2023/2024 办法，**2026 列表 0 条**；带 `year=2026`：9 条全部来自 2026 列表 |
| E6 空/空白内容 | 空文本、纯空白文本、空向量、零向量全部被 `ValueError` 拒绝；`replace_document(id, [])` 正确清空旧记录 |
| E7 元数据过滤 | 无过滤 10 条（2025×5、2026×4、2023×1）；`document_type=竞赛列表` 10 条；`year=2026` 9 条；`year=1999` 0 条；`top_k=50` 命中 1 个文档时返回 1 条 |
| E8 来源可追溯 | 修复后 prompt 含 `来源文件` 与 `适用年份`；`chunk_hash` 未泄漏 |
| E9 修复前/后同 query 对比 | top_3：0/4 → 0/4；top_5：3/4 → 3/4；top_10：3/4 → 3/4（**排名未变**，见下方说明） |
| E10 逐 chunk 分数对比 | 2026 列表 9 个 chunk 中 8 个分数上升，最大 +0.043542，1 个 −0.003380 |

**本轮重跑记录（2026-10-17，数据集修正后）**：

| 命令 | 退出码 | 摘要 |
| --- | --- | --- |
| `python -m unittest discover -s backend -t . -p "test_*.py"` | **0** | `Ran 128 tests in 16.723s` → OK |
| `python tools/rag_verification/verify_inventory.py` | **0** | 10 份文档 / 45 条断言 → PASS |
| `python tools/rag_verification/verify_rag.py` | **0** | E1 75 chunks、E2 重复 ID 0 → PASS、E10 8/9 上升 |
| `python tools/rag_verification/check_retrieval.py` | **0** | 24 题；18 道有期望文档的题全部进 top_3；负样本 0.5349–0.6590 |

**关于 E9 的诚实说明**：修复前后 top_k 命中数**没有变化**。
原因是受影响的那条 2026 chunk 原本就排在第 5 名，+0.0435 的分数提升不足以让它挤进前 3。
所以 P1 的修复价值是"消除了一个确定存在的向量畸变 + 让存储文本正确"，
**不是**"把检索准确率提高了"。把它说成准确率提升是夸大。

**关于 E4 的诚实说明**：3/4 只是"人工标注的名字恰好出现在返回的 chunk 文本里"，
`evaluate_retrieval.py` 自己也声明这是审查辅助项而非相关性判定。
本次验收的是**流程与来源可追溯性**，不是准确率指标。

### 2.4 语料来源核验

```powershell
python tools/rag_verification/verify_inventory.py
# documents checked: 10   text claims verified: 45
# PASS: every inventory claim matches the shipped documents.
```

该校验同时锁定 10 份 PDF 的 sha256、页数、`/CreationDate`、抽取字符数，
以及文号/日期/适用条款等 45 条原文断言。任何一份文档被替换都会立刻失败。

### 2.5 带标准答案的问题集与检索核对记录（阶段二补充）

`backend/knowledge/evaluation_dataset.json` 由 1 条扩到 **24 条**：
17 条可答（含跨年份区分）、4 条真语料缺口（`not_in_corpus`）、
1 条抽取不可靠案例、1 条适用范围陷阱；原 `q1` 保持原样未动。
新增字段为 `expected_behaviour` / `expected_document_ids` / `ground_truth_points`。

阶段三修正了其中两条错误的标注：`q18`（转专业）与 `q20`（补考/重修）原本被标为
「语料缺口」，实际内容写在《非航海类专业本科生学籍管理规定》里，
现已改为 `answerable` 并补上逐字条款与期望文档；同时补入两条真正的负样本——
`q23`（医疗报销）与 `q24`（勤工助学），它们的主题在 10 份文档中确实 0 命中。

`tools/rag_verification/check_retrieval.py` 用真实向量模型跑全部问题，
输出逐题记录（含分数、`document_id`、来源文件、命中哪些标准答案要点，
以及留白的人工核对栏）：`tools/rag_verification/reference/retrieval-check-record.txt`。

实测（真实 `bge-small-zh-v1.5`，临时 Chroma 目录，`top_k=5`）：

| 指标 | 结果 |
| --- | --- |
| 有期望文档的题目 | 18 |
| 其中期望文档进入 **top_3** 的 | **18 / 18** |
| 语料缺口题（4 条）第一名分数区间 | **0.5349 – 0.6590** |
| 可答题第一名分数区间 | **0.6346 – 0.8076** |
| 两个区间是否重叠 | **重叠**：可答题里最低的 `q20`（0.6346）低于最强负样本 `q19`（0.6590） |
| 跨年份混检 | `q15` 的 #1 是 **2025 列表**，2026 列表到 #2 才出现；`q17` 的 #1 也是 2025 列表 |
| 范围陷阱 | `q22`「航海类专业学生的综合素质测评」的 #1 是**仅适用信息学院 2025-2 中队**的细则 |

**这组数字说明什么**：18/18 只说明检索指向了正确的文档，**不是准确率**——
标准答案不完整、出题人与读文档的是同一人、返回的 chunk 还没有人逐条判定。
关于 L3（无最低分阈值）：修正标注后，负样本的最高分从 0.7379 降到 **0.6590**
（因为 0.7379 原本来自被误标的那道题），但**两个区间仍然重叠**——
可答题里最低的 `q20`（0.6346）比最强负样本还低。
也就是说，不存在一个阈值能同时接住全部可答题、又拒掉全部负样本；
而链路本身连阈值都没有，分数整体挤在 0.53–0.81 的窄带里，
单看分数分不出"有据可依"与"最接近的无关片段"。

---

## 3. 发现的问题及修复记录

| 编号 | 严重度 | 问题 | 状态 | 改动文件 |
| --- | --- | --- | --- | --- |
| P1 | 高 | 2026 列表以康熙部首兼容字符抽取，索引与查询向量不一致 | **已修复** | `pdf_loader.py`、`embedding.py` |
| P2 | 中 | `ingest_pdf_to_store` 忽略 `max_chars` | **已修复** | `ingest.py` |
| P3 | 高 | RAG prompt 丢失文档来源与年份 | **已修复** | `prompt_builder.py` |
| O1 | 高 | 生产链路不使用 `metadata_filter`，跨年份资料混检 | 待决策 | 需动 `main.py`，超出本次范围 |
| O2 | 中 | 中队级实施细则全库可检索 | 待决策 | 建议走 O1 的元数据过滤 |
| O3 | 中 | 请假单（表单）作为知识资料入库 | 待决策 | 建议加 `document_type` 并在检索侧排除 |
| L1 | 中 | 竞赛列表按列分离抽取，chunk 丢失行归属 | 已知局限 | 需表格解析，超出边界 |
| L2 | 中 | 评估集仅 1 条 query | **已缓解** | 已扩到 24 条并有核对记录（见 2.5）；仍非基准，不做准确率外推 |
| L3 | 中 | 空结果与低分结果不可区分（无阈值、clamp 到 0） | 已知局限 | 建议加可选 `min_score` |
| L4 | 中 | 仓库不记录文档来源信息 | 已缓解 | 新增来源清单 + 自动校验；建议纳入入库 metadata |
| O4 | 高 | 默认 `top_k=3` 漏掉文末的范围/施行条款，模型据此自行推断并给出错误答案 | 待决策 | 见 `OPEN_ISSUES.md` P0-2 |
| P5 | 中 | NFKC 不覆盖 CJK 部首补充（U+2E80–U+2EFF），2026 列表残留 8 个字符 / 23 处 | 待决策 | `pdf_loader.py`、`embedding.py` |

### 3.1 修复的兼容性说明

- `embedding.embed_text` / `pdf_loader.load_pdf_text` **签名未变**，只改了内部归一化。
  **行为变化**：入库文本与查询文本会被 NFKC 归一化。对绝大多数中文/英文文本无影响，
  对全角字符（`（）`→`()`、`：`→`:`）会改变存储文本。
- `prompt_builder.build_rag_prompt` **签名未变**。
  **行为变化**：当 metadata 含 `source` 等字段时，资料头会多一个括号标注。
  只有一个既有测试依赖旧的精确前缀
  （`test_multiple_chunks_are_included`），已按新语义拆分/更新；
  新增 `test_chunks_without_metadata_keep_the_bare_header` 锁定"无 metadata = 旧格式"。
- `ingest.ingest_pdf_to_store` **新增可选参数** `max_chars=DEFAULT_MAX_CHARS`，
  默认行为与旧版一致，旧调用点无需改动。
- 未改动任何公共返回值结构、异常类型或 `SearchResult` / `VectorRecord` 定义。

### 3.2 重新入库的执行情况（阶段三已完成）

P1、P2、P3 中：

- **P3 立即生效**：prompt 组装在查询时进行，不需要重新入库。
- **P1、P2 需要重新生成 Embedding**：阶段三已执行——用修复后的代码从 10 份 PDF
  重新构建了向量库（75 条 / 10 份文档），并随本次提交纳入版本控制（`data/chroma/`）。
  因此仓库里的向量库**不再带旧缺陷**：NFKC 归一化已作用于索引侧文本，
  `max_chars` 也已正确透传。
- 重建方式：`python -m backend.knowledge.build_index`（幂等、可重复执行、不会删库）；
  只产出文本与切片、不碰向量库的是 `python -m backend.knowledge.export_chunks`。
- 复核方式：`verify_rag.py`（E1–E10）与 `verify_inventory.py`（45 条来源断言）。
  本次已复核：128 个用例全部通过，且库中记录数 / 切片文件行数 / 文本文件数三者一致。

### 3.3 阶段三新增的发现

1. **默认 `top_k=3` 会漏掉文末的范围/施行条款（上表 O4，高优先）**
   - 实测：问「推免办法适用于哪些年级」，模型答「2025 届 / 通常对应 2021 级」——**错误**；
     原文是「第十五条 …适用于 **2022 级及以后**年级本科学生」。
   - 根因：该条款位于 `chunk_index=3`，在 `top_k=5` 时排第 **5** 位，
     而主流程默认只取 3 条 → 条款根本没进 prompt，
     模型于是按「应届毕业生」自行推断，并附上了文号与印发日期，**看起来完全可信**。
   - 这是目前最危险的一类错误：有出处、语气确定，但内容错。

2. **NFKC 覆盖不全（上表 P5）**
   - NFKC 能修「康熙部首」（U+2F00–U+2FDF），但修不了「CJK 部首补充」（U+2E80–U+2EFF）。
   - 2026 竞赛列表里仍残留 **8 个字符、23 处**：`⺠`(民)、`⻄`(西)、`⻋`(车)、`⻔`(门)、
     `⻘`(青)、`⻚`(页)、`⻛`(风)、`⻰`(龙)；逐个验证过 NFKC 对它们无效（`U+2EA0 → U+2EA0`）。
   - 规模约为当初 631 处的 1/27，但机理相同：这些词的向量仍与正常输入的查询不一致。

3. ~~问题集有两处标注错误~~ **已修正**：`q18`（转专业）、`q20`（补考/重修）
   已改为 `answerable` 并补上逐字条款与期望文档，同时补入两条真负样本
   （`q23` 医疗报销、`q24` 勤工助学）；问题集由 22 条增至 24 条。详见 2.5 节。

以上三条都已登记在 [`OPEN_ISSUES.md`](OPEN_ISSUES.md)。

---

## 4. 使用的知识材料来源

10 份 PDF 全部位于 `backend/knowledge/documents/`。
完整可核验清单见 [`document-inventory.json`](tools/rag_verification/document-inventory.json)，
由 `verify_inventory.py` 自动校验。下表是摘要（文号/日期均为**原文抽取**所得）：

| # | 文件 | 文号 | 发布/施行 | 适用范围（原文） | 状态 |
| --- | --- | --- | --- | --- | --- |
| 1 | 附件1.《…竞赛列表(2026年)》.pdf | 无 | PDF `/CreationDate` 2026-03-31 | 2026 年度认定竞赛列表 | 内容与文件名一致；无发文机关署名 |
| 2 | 附件.《…竞赛列表(2025年)》.pdf | 无 | PDF `/CreationDate` 2025-07-23 | 2025 年度认定竞赛列表 | 对 2026 年问题已属历史资料 |
| 3 | …《大学生创新创业竞赛管理办法》的通知.pdf | 连海大办字〔2023〕7 号 | 2023-07-06 | 全校；A/B/C 三类定义在第四条 | 现行（第四条声明附件定期修订） |
| 4 | …大学生科技创新奖励办法（正文）.pdf | 连海大办字〔2024〕5号 | 2024-04-24 施行 | 全日制在籍本科生 | 现行；废止〔2019〕20号 |
| 5 | …《推荐优秀应届本科毕业生免试攻读硕士研究生办法》的通知.pdf | 连海大办字〔2025〕1号 | 2025-01-16 印发，2025-01-10 施行 | **适用于 2022 级及以后年级本科学生** | 现行；废止 5 份旧文 |
| 6 | …《非航海类专业本科生学籍管理规定》的通知.pdf | 连海大办字〔2021〕13 号 | 2021-11-05 印发，2021-11-10 施行 | 非航海类专业普通全日制本科生 | **较旧（2021）**，无法在仓库内核实是否有新版 |
| 7 | 大连海事大学本科生奖学金评定办法.pdf | 连海大办字〔2023〕13 号 | 2023-07-12 施行 | 在籍全日制本科学生 | 现行；含 3 个附件细则 |
| 8 | 大连海事大学学生违纪处分办法.pdf | 连海大校发〔2022〕194 号 | 2022-09-11 施行 | 研究生、本科生；继续教育/港澳台侨/留学生参照 | 现行（2022） |
| 9 | 2025-2中队本科生综合素质测评实施细则.pdf | 无 | 2025-10-01 施行 | **仅信息科学技术学院 2025 级 2 中队** | **超窄适用范围**，需过滤 |
| 10 | 大连海事大学学生离校请假单.pdf | 无 | 无日期 | 表单，非制度文件 | 建议不作为制度资料 |

### 4.1 已标记的过期/无法核实材料

- **#2 2025 竞赛列表**：对 2026 年问题属历史资料。已标记，未删除。
- **#6 学籍管理规定（2021）**：发布时间较久。**未在仓库内找到更新版本，
  也无法在本次离线环境下核实校外最新版本**，因此标记为"未核实是否现行"，
  未自行推断其效力。
- **#1 2026 竞赛列表**：文件名与内容自洽，但**文档本身没有发文机关署名与文号**，
  因此"由哪个部门发布"无法从仓库核实。已在清单中记为 `null` 并注明原因，
  **没有编造发文单位**。
- **#9 测评细则**：无文号、无发布日期的非正式下发文件，
  `year=2025` 属于入库时的归类，不等于发布日期。
- **#10 请假单**：无日期，属于表单模板，`year=2025` 是入库时的假设。

### 4.2 语料覆盖缺口

**已核实确实不在知识库内的主题**（判定方法是先剔除全部空白再检索，
避免硬换行把词拆断造成假阴性）：培养方案 / 课程计划、考试安排、
医疗保障、大学生创新创业训练计划（大创）项目管理办法、
2026 年校内竞赛的报名时间 / 截止日期。
也就是说，很多学生会问的问题本来就无资料可检索。

> **本节更正（阶段三）**：早前版本把「转专业办法」也列入缺口，并把问题集中的
> `q18`（转专业）、`q20`（补考/重修）标为 `not_in_corpus`，这是**错误的**——
> 这两类内容就写在《非航海类专业本科生学籍管理规定》里：
> 去掉空白后检索，`转专业` 命中 2 份文档、`补考` 1 份、`重修` 3 份。
> 当初的检查是逐行 grep，而抽取文本是硬换行的，`转专` / `业` 被拆到两行导致漏判。
> 问题集这两条标注**已在阶段三修正**（改为 `answerable` 并补上条款原文，
> 另加两条真负样本），核对记录已重新生成。

---

## 5. 尚未验证的风险

1. **跨年份误答（最高优先）**：O1 未修复。虽然 P3 让模型能看到年份标签，
   但 `metadata_filter` 仍未接入主流程，候选集依然混着 2025/2026 两份列表。
   实测已证明"问 2026 年，top_3 全是 2025/2023/2024 的资料"。
2. **`replace_document` 的非原子性**：upsert 与 delete 之间无事务，
   中途失败会留下新旧混合的 chunk。没有测试覆盖，也没有失败告警。
3. **`document_id` 依赖文件绝对路径**：换目录/换机器重新导入会产生两套记录。
   本次验证的脚本用显式 `document_id` 规避，但 `ingest_document.py` 的 CLI
   默认仍是路径。**未验证**在生产路径下是否已发生过该问题。
4. **表格类文档的检索质量**：L1 未验证"按行重建"能带来多少提升，
   也未量化当前列错位对回答正确率的影响。
5. **未做端到端回答质量验证**：本次**没有**调用真实 DeepSeek API，
   所有结论都止于"prompt 里有什么、检索返回什么"。回答是否真的更准确、是否真的会引用来源，
   **未验证**。
6. **未验证其他 PDF 生成器**：NFKC 修复只对 `U+2E80–U+2FDF` / `U+F900–U+FAFF` /
   `U+FE30–U+FE4F` 区间内会被 NFKC 改写的字符有效。
   如果将来出现其他形式的乱码（例如 CID 字体映射错误、竖排错位、缺字 `U+FFFD`），
   当前护栏检测不到。`test_knowledge_documents.py` 的字符区间检查需要随之扩展。
7. **`embedding` 模型的沉默降级**：`_get_model()` 加载失败会抛 `EmbeddingError`，
   但 `embed_text` 对**非空文本返回空向量**的唯一路径是空白输入。
   如果模型对某个 chunk 返回空结果，`ingest` 会把空向量交给 `ChromaRecord`，
   由 `_validate_vector` 抛出 `ValueError` —— 这个分支**未实测**（真实模型下未出现）。
8. **并发写入未验证**：多个进程同时 `replace_document` 同一文档的行为未测试。
9. **Windows/文件路径大小写**：`os.path.normcase` 在 Windows 上会小写化，
   在 Linux 上不会。同一批文档在两个平台上会得到不同的 `document_id`。
   **未验证**是否已有跨平台数据，也未给出统一的 ID 规范。
10. **评估集扩充后结论可能变化**：E4 的 3/4 不能外推为整体表现（见 2.3 的诚实说明）。

---

## 6. 交付物索引

| 文件 | 内容 |
| --- | --- |
| `RAG_VERIFICATION.md` | 本报告 |
| `PULL_REQUEST.md` | PR 描述。分支 `feat/rag-verification` 已推送到 origin，PR 在 GitHub 网页端创建：`https://github.com/kento-wts/DMU-AI-Learning-Assistant/pull/new/feat/rag-verification`（顶端提交以 `git log` 为准） |
| `OPEN_ISSUES.md` | 当前未解决的问题与待决策事项 |
| `backend/knowledge/build_index.py` | PDF → 向量库（批量、幂等、显式 document_id） |
| `backend/knowledge/export_chunks.py` | PDF → 抽取文本 + 切片文件（不碰向量库） |
| `data/chroma/`、`data/exports/` | 已提交的向量库与各阶段产物（75 条 / 10 份文档） |
| `backend/knowledge/pdf_loader.py` | P1 修复：每页文本 NFKC 归一化 |
| `backend/knowledge/embedding.py` | P1 修复：`normalize_for_embedding`，索引/查询双侧一致 |
| `backend/knowledge/prompt_builder.py` | P3 修复：资料块携带来源/类型/年份/ID |
| `backend/knowledge/ingest.py` | P2 修复：`max_chars` 透传 |
| `backend/knowledge/test_knowledge_documents.py` | 语料级回归护栏（新增） |
| `backend/knowledge/test_pdf_loader.py` 等 4 个测试文件 | 见 2.2 表格 |
| `tools/rag_verification/README.md` | 验证脚本使用说明 |
| `tools/rag_verification/document-inventory.json` | 可核验的知识材料来源清单 |
| `tools/rag_verification/verify_inventory.py` | 清单自动校验（45 条文本断言 + 校验和） |
| `tools/rag_verification/verify_rag.py` | E1–E10 全流程真实向量实验 |
| `tools/rag_verification/reference/` | 本次运行的真实输出存档 |
| `backend/knowledge/evaluation_dataset.json` | 带标准答案的问题集（24 条，阶段二扩展 + 阶段三修正） |
| `tools/rag_verification/check_retrieval.py` | 逐题检索核对脚本（写临时 Chroma，不碰 `data/chroma`） |
| `tools/rag_verification/reference/retrieval-check-record.txt` | 检索结果核对记录（含人工核对栏） |

## 7. 建议的下一步（按优先级）

1. **决策 O1**：确定年份/专业过滤的接入方式，然后我单独开分支实现（含降级策略）。
2. ~~扩充 `evaluation_dataset.json` 到 ≥20 条~~ **已完成**（24 条，见 2.5 节）。
   下一步是人工逐条核对返回的 chunk，并据此为 O1（年份过滤）与 L3（最低分阈值）定策略。
3. 评估表格解析（L1），决定是用版面解析库还是针对竞赛列表写行重建。
4. 把 `issue_date` / `issuing_body` / `applicable_scope` 纳入入库 metadata（L4）。
5. 给 `replace_document` 增加失败回滚或至少一致性自检。
6. ~~统一 `document_id` 规范，去掉对绝对路径的隐式依赖~~ **已完成**：
   `build_index.py` 的入库流程一律使用显式 `document_id`，
   不再依赖 `ingest_pdf_to_store` 那个「归一化绝对路径」的默认值。
7. 决定默认 `top_k` 是否提高到 5~8（O4），以及是否引入最低分阈值（L3）——见 `OPEN_ISSUES.md`。
8. 修正 `evaluation_dataset.json` 中 `q18` / `q20` 的错误标注，并补两个真负样本（P1-1）。
9. 补一张 CJK 部首补充（U+2E80–U+2EFF）的映射表（P5）。
