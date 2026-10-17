# 知识库产物与仓库交付策略

- 分支：`feat/rag-artifacts-policy`（基于 `feat/rag-retrieval-quality`，stacked PR）
- 日期：2026-10-17
- 一句话：**源 PDF 入库，索引与导出不入库**；克隆后按 README 跑一次构建即可，已在干净克隆上实测通过。

## 1. 三类文件

| 类别 | 文件 | 处理 |
| --- | --- | --- |
| **权威源** | `backend/knowledge/documents/*.pdf`（10 份，2.99 MB） | **入库** |
| 生成物 | `data/chroma/`（≈3.8 MB）、`data/exports/`（≈380 KB） | **不入库**，脚本重建 |
| 验证证据 | `tools/rag_verification/reference/*`（≈180 KB） | **入库**（只含占位符路径） |
| 本地环境 | `.env`、`frontend/node_modules/`、会话工作目录 | 始终不入库 |

## 2. 逐项评估

| 文件 | 必要性 | 体积 | 敏感性 | 可再生成性 |
| --- | --- | --- | --- | --- |
| 源 PDF（10 份） | **必需**：唯一权威输入 | 2.99 MB | 见第 4 节（含校内联系人电话/邮箱） | ❌ 不可再生成（原始材料） |
| `data/exports/text/*.txt` | 可选：便于人工核对抽取质量 | ≈180 KB | 与源 PDF 同源，**不新增**信息 | ✅ `export_chunks`，约 4 秒 |
| `data/exports/chunks.jsonl` + `overview.md` | 可选：便于查看切片与元数据 | ≈200 KB | 同上 | ✅ 同上 |
| `data/chroma/`（sqlite + HNSW 二进制） | 可选：运行所需，但可由源重建 | ≈3.8 MB | 无额外信息（文本 + 向量） | ✅ `build_index`，约 10 秒 |
| `tools/rag_verification/reference/*`（报告） | **证据**：报告里的数字与条款引用靠它复核 | ≈180 KB | 只含占位符路径 | ⚠️ 可重跑，但结果依赖当时的代码/模型，重跑不等于当时的记录 |

## 3. 决策：不提交 Chroma 索引与导出文件

理由：

1. **二进制不可 diff**：`chroma.sqlite3` 与 HNSW 索引每次重建都整块变化，review 时看不到任何有意义的信息，只会让 PR 体积膨胀。
2. **会悄悄过期**：换 embedding 模型、改分块参数、加一份 PDF 之后，仓库里那份索引就与源文件不一致，而"仓库里有库"本身会让人误以为可以直接用。
3. **重建成本低**：10 秒（含模型加载）+ 4 秒，远小于维护一份二进制产物的代价。
4. **冗余**：导出文本是 PDF 的派生内容，两者同时入库只会产生"改了一边忘了另一边"的分歧。

代价与缓解：

- 克隆后必须执行一次 `python -m backend.knowledge.build_index`，README「快速开始」第 3 步已写明。
- 首次构建需要下载 `bge-small-zh-v1.5`（约 90 MB）。离线环境需预先准备模型缓存并设置 `EMBEDDING_CACHE_DIR`。
- 不执行构建时检索返回空、回答会变成"知识库没有检索到相关资料"——这是显式失败，不是静默错误。

## 4. 敏感性与公开权限（需要负责人确认）

- 10 份 PDF 是学校发布的竞赛名单、管理办法、学籍规定等校内材料。
- 实测：**竞赛列表内含 42 个手机号、65 个邮箱**（各竞赛的校内负责人联系方式）。
  这些信息本来就写在源 PDF 里，导出文本只是同样的内容，**不会新增暴露面**；
  但由于导出文件不再入库，文本形式不再随仓库分发。
- **风险**：本仓库托管在公开的 GitHub 仓库上。若学校认为联系人手机号/邮箱不宜公开，
  需要处理的是**源 PDF 本身**（以及既有提交历史），而不是导出文件。这属于负责人的决策，
  本次没有删除或改写任何源 PDF。
- 导出文件与 chunk 文件未发现身份证号、成绩单等其它个人敏感字段。

## 5. 干净克隆重建验证（实际执行）

在临时目录克隆本分支（不包含任何本地未跟踪文件）：

```
git clone --branch feat/rag-artifacts-policy --single-branch <repo> clone-check-115700
```

克隆后确认：

| 检查 | 结果 |
| --- | --- |
| `data/chroma` | **不存在** |
| `data/exports` | **不存在** |
| `.env` | 不存在 |
| `frontend/node_modules` | 不存在 |
| 源 PDF | 10 份 |

按 README 执行：

| 命令 | 实际输出 | 退出码 |
| --- | --- | --- |
| `python -m backend.knowledge.build_index` | `documents imported: 10`、`total chunks: 75`、`collection size: 75` | **0** |
| `python -m backend.knowledge.export_chunks` | `chunks: 75`、`text chars: 67792`、写出 3 类文件 | **0** |
| `python -m unittest discover -s backend -t . -p "test_*.py"` | `Ran 154 tests in 18.462s` → **OK** | **0** |

重建产物体积：`data/` 共 17 个文件、2.44 MB（新建的 sqlite 比增量更新过的更紧凑）。

## 6. 一致性校验（重建后）

```
db records: 75   jsonl rows: 75
same document set: True
per-document equal: True
documents: 10
metadata keys: ['chars','chunk_hash','chunk_index','document_id','document_type','major','source','text','year']
```

两个脚本共用同一套 `load_pdf_text` / `chunk_text`，所以库中块数与导出文件逐文档相等。

## 7. 报告去个人路径

`verify_rag.py` 与 `check_retrieval.py` 原先会把本机绝对路径写进报告
（`C:\Users\...`、`C:\Users\...\Temp\...`）。现已改为占位符
（`<repo root>`、`<temp>/chroma`），两份已入库的报告也已重新生成：

- 不再泄露个人机器路径；
- 重跑时不再产生"只差一行路径"的无意义 diff。

## 8. 剩余风险

1. **仓库公开 + 源 PDF 含联系人信息**（第 4 节），需负责人决定是否需要脱敏或限制仓库可见性。
2. 首次构建依赖模型下载；无网络且无缓存时 `build_index` 会以 `EmbeddingError` 失败（错误明确，但会挡住新手）。
3. 索引不入库后，代码评审看不到"内容变化"；只能依赖测试、报告与 `export_chunks` 的输出。
4. 既有的提交历史里仍包含之前提交过的导出文件（`42c54b9` 起）。本次只是不再跟踪，
   **没有改写历史**；如需彻底移除需另行决定。
5. 本策略未覆盖 `frontend/node_modules` 的获取方式（需 `npm ci` + Node ≥18）。
