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

## Reference output

`reference/` holds the artefacts produced during the `feat/rag-verification`
work:

| File | Produced by |
| --- | --- |
| `baseline-verification-report.txt` | `verify_rag.py` |
| `inventory-verification.txt` | `verify_inventory.py` |
| `pdf-extraction-dump.txt` | `dump_pdf_meta.py` |
| `pdf-inventory.json` | `dump_pdf_meta.py` |
| `pdf-text/` | `dump_pdf_meta.py` (git-ignored, regenerable) |

All three scripts rewrite the file they own. That is expected; only commit a
change when the new output is the one you intend to stand behind.

## Interpreting the numbers honestly

- The name-overlap check in E4/E9 is a **review aid**, not a relevance verdict,
  and not recall. `backend/knowledge/evaluate_retrieval.py` says the same thing.
- E9 shows **no change in top-k hit counts**. The repair in P1 corrects a
  definite vector defect (E3, E10) but does not by itself move the ranking of the
  one curated query. Do not report it as an accuracy improvement.
- The curated dataset has exactly one query. No overall accuracy figure can be
  derived from it.
