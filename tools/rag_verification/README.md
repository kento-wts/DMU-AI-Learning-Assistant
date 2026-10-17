# RAG verification tools

Read-only verification tooling for the knowledge base. Nothing here is part of
the running backend; these scripts exist so the claims in
[`../../RAG_VERIFICATION.md`](../../RAG_VERIFICATION.md) can be re-checked on any
machine.

**No script writes to the repository's own vector index.**
`verify_rag.py` builds every corpus inside a `tempfile.TemporaryDirectory()`, so
`data/chroma/` is never opened, created, or modified.

## Requirements

Same as the backend, plus nothing extra:

```powershell
python -m pip install -r ../../backend/requirements.txt
```

`verify_rag.py` loads the real local embedding model
(`BAAI/bge-small-zh-v1.5`, 512 dimensions) and downloads it on first use.
Set `EMBEDDING_CACHE_DIR` to control where it is cached.

## Scripts

### `dump_pdf_meta.py` — read-only document inspection

```powershell
python tools/rag_verification/dump_pdf_meta.py
```

Writes `reference/pdf-text/*.txt` (one extracted text file per PDF),
`reference/pdf-inventory.json` (page counts, sha256, PDF `/CreationDate`,
text head) and `reference/pdf-extraction-dump.txt` (a readable digest of the
same). Use this when you need to read a source document's actual wording.

Prefer this script over shell redirection for those files: PowerShell's `>`
writes UTF-16, which git then treats as binary and which the other tools cannot
read back as UTF-8.

### `verify_inventory.py` — provenance claim check

```powershell
python tools/rag_verification/verify_inventory.py
```

Reads `document-inventory.json` and asserts that every recorded claim still
holds for the shipped files: sha256, page count, `/CreationDate`, extracted
character count, and each verbatim text quote (文号 / 印发日期 / 施行条款 /
适用范围条款). Exit code 0 = all claims verified. It also refreshes
`reference/inventory-verification.txt`.

This is the guard against a document being silently swapped.

### `verify_rag.py` — end-to-end experiments E1–E10

```powershell
python tools/rag_verification/verify_rag.py
```

Builds a throwaway Chroma corpus from all 10 PDFs with the real embedding
model, then runs:

| ID | Experiment |
| --- | --- |
| E1 | real-model ingest of every document; chunk counts and bounds |
| E2 | ingest the whole corpus twice; duplicate / idempotency check |
| E3 | Kangxi-radical damage measurement on the 2026 list |
| E4 | curated evaluation query at top_k = 3 / 5 / 10 |
| E5 | year-scoped query; does top-k mix the 2025 and 2026 lists? |
| E6 | empty / whitespace-only content handling |
| E7 | metadata filtering, including a filter with no matches |
| E8 | provenance surviving into the built RAG prompt |
| E9 | pre-fix vs Phase 2 corpus, same query (ground-truth overlap) |
| E10 | per-chunk cosine delta caused by the compatibility-character repair |

E9 builds its "pre-fix" corpus by re-implementing the old extraction and
embedding steps locally (`_load_pdf_text_raw`, `_embed_text_raw`) against the
current source tree, so the comparison does not require reverting the fix.

Results print to stdout and are also written to
`verification-report.txt` (git-ignored) and to
`reference/baseline-verification-report.txt` (committed).

### `check_retrieval.py` — retrieval check record for the curated questions

```powershell
python tools/rag_verification/check_retrieval.py
```

Builds a throwaway corpus and runs every question in
`backend/knowledge/evaluation_dataset.json` through the real `Retriever`, then
records, per question: the curated expectation, every returned chunk with its
score / `document_id` / source file, and which curated ground-truth points
appear verbatim in the returned text. Each entry ends with a blank human-review
line, so the file doubles as a tick-off sheet.

Like `verify_rag.py`, it never opens `data/chroma`. Output goes to
`retrieval-check-record.txt` (git-ignored) and to
`reference/retrieval-check-record.txt` (committed).

## Curated question set

`backend/knowledge/evaluation_dataset.json` holds the questions with their
standard answers. Every entry has `id`, `question` and `notes`; entries added
for the review also carry:

| Field | Meaning |
| --- | --- |
| `expected_behaviour` | `answerable` / `not_in_corpus` / `scope_mismatch` / `not_reliably_answerable_from_text` |
| `expected_document_ids` | the document(s) the answer must come from; empty means "should not be answered from the corpus" |
| `ground_truth_points` | verbatim statements the answer has to contain, each of which `verify_inventory.py` can re-check against the shipped PDFs |

`q1` is the original entry and keeps its historical `relevant_competitions`
field so `backend/knowledge/evaluate_retrieval.py` still renders it unchanged.

The set is a **spot-check sample, not a benchmark**: 18 questions have an
expected document, 4 are genuine corpus gaps, 1 is an extraction-unreliable
case and 1 is a scope trap. No accuracy, recall or precision figure may be
derived from it.

> Two entries used to be mislabelled as corpus gaps (`q18` 转专业, `q20` 补考/重修);
> that content is in the non-navigation status rules, and the earlier "0 hits"
> reading came from a line-based grep that misses words split across hard line
> breaks. Both are now `answerable` with verbatim clauses, and two real gaps
> (`q23` medical reimbursement, `q24` work-study jobs) replaced them.

## Reference output

`reference/` holds the artefacts produced during the `feat/rag-verification`
work:

| File | Produced by |
| --- | --- |
| `baseline-verification-report.txt` | `verify_rag.py` |
| `retrieval-check-record.txt` | `check_retrieval.py` |
| `inventory-verification.txt` | `verify_inventory.py` |
| `pdf-extraction-dump.txt` | `dump_pdf_meta.py` |
| `pdf-inventory.json` | `dump_pdf_meta.py` |
| `pdf-text/` | `dump_pdf_meta.py` (git-ignored, regenerable) |

All three scripts rewrite the file they own. That is expected; only commit a
change when the new output is the one you intend to stand behind.

`reference/baseline-verification-report.txt` and
`reference/retrieval-check-record.txt` open with **placeholder** paths
(`<repo root>`, `<temp>/chroma`) rather than the absolute paths of the machine
that produced them, so the committed copies carry no personal path and do not
churn between runs. Everything below them is measured output; the metadata dump
is key-sorted so it stays stable across re-runs.

## Interpreting the numbers honestly

- The name-overlap check in E4/E9 is a **review aid**, not a relevance verdict,
  and not recall. `backend/knowledge/evaluate_retrieval.py` says the same thing.
- E9 shows **no change in top-k hit counts**. The repair in P1 corrects a
  definite vector defect (E3, E10) but does not by itself move the ranking of the
  one curated query. Do not report it as an accuracy improvement.
- `check_retrieval.py` reached the expected document in top_3 for every one of
  the 18 questions that have an expected document. That is a smoke test that
  retrieval is pointed at the right documents, **not** an accuracy figure: the
  ground truth is partial, the questions were written by the same person who
  read the documents, and nobody has judged the returned chunks yet.
- The corpus gaps are the interesting part. The question "大学生创新创业训练计划
  （大创）项目应该怎么申报" really is absent from all ten documents, yet it still
  returns a chunk scoring **0.6590** - while the weakest genuinely answerable
  question scores **0.6346**. The two ranges overlap, so no single cut-off can
  keep every answerable question *and* reject every unanswerable one, and the
  pipeline has no minimum-score threshold at all. Treat a low score as unproven
  rather than as an answer, and do not quote a threshold as policy until the
  owner sets one.
- **Correction**: an earlier version of this note used "转专业的申请条件是什么" as
  the corpus-gap example and quoted 0.7379. That topic *is* covered by the
  non-navigation status rules, so the example was wrong (same root cause as the
  two entries that were mislabelled and have since been fixed). With the
  corrected set the strongest negative is 0.6590 and exactly one answerable
  question (0.6346) falls below it - the overlap is narrower but still real.
