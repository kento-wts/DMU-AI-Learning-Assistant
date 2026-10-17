"""Compare retrieval at several top_k values and study score thresholds.

For every question in ``backend/knowledge/evaluation_dataset.json`` this builds
a throwaway corpus with the real embedding model and records, per ``top_k``:

* whether the expected document reached the returned set,
* how many curated ground-truth points appear in it, and at which rank the first
  one appears (this is what "the key clause was missed" means concretely),
* for questions with no answer in the corpus, the best score and how much
  material was still returned.

It then sweeps score cut-offs and reports **false rejects** (answerable
questions whose best hit is below the cut-off) against **false accepts**
(corpus-gap questions whose best hit is above it).

None of this is an accuracy metric. A hit only means the text was retrieved;
whether an answer is correct still needs a human.

Run from the repository root:

    python tools/rag_verification/compare_top_k.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import verify_rag as harness  # noqa: E402  (same directory: reuses the corpus builder)

from backend.knowledge.chroma_store import ChromaVectorStore  # noqa: E402
from backend.knowledge.embedding import embed_text  # noqa: E402
from backend.knowledge.pdf_loader import load_pdf_text  # noqa: E402
from backend.knowledge.retriever import Retriever  # noqa: E402

DEFAULT_TOP_KS = (3, 5, 8)
DEFAULT_THRESHOLDS = tuple(round(0.50 + 0.01 * step, 2) for step in range(31))
OUTPUT_PATH = Path(__file__).resolve().parent / "reference" / "top-k-comparison.txt"

# The clause that carries the applicable scope of the recommendation rules. It
# sits in the last chunk of that document, which is why "the key clause was
# missed" is a real failure mode - but only for some phrasings, so both are
# probed here instead of assuming one.
SCOPE_CLAUSE = "适用于2022级及以后年级本科学生"
KEY_CLAUSE_PROBES = (
    ("2026-10 E2E phrasing", "推荐优秀应届本科毕业生免试攻读硕士研究生的办法适用于哪些年级？"),
    ("curated q13 phrasing", "推免办法适用于哪些年级的本科学生？"),
)


def category_of(entry: dict) -> str:
    """Map one dataset entry to one of the four review categories."""
    behaviour = entry.get("expected_behaviour")
    if behaviour == "not_in_corpus":
        return "语料缺失"
    if behaviour == "scope_mismatch":
        return "范围不匹配"
    if behaviour == "not_reliably_answerable_from_text":
        return "部分可答（抽取受限）"
    if behaviour == "answerable":
        if entry.get("completeness") == "partial":
            return "部分可答"
        return "完全可答"
    return "未分类"


_LEADING_LABEL = re.compile(r"^[^：:]{1,10}[：:]")


def normalise(text: str) -> str:
    """NFKC-normalise and drop **all** whitespace before a substring check.

    The curated points are written for humans: they may carry a label of ours
    ("文号：连海大办字…") and a space where the PDF extraction has none
    ("第十五条本办法自…"). Removing all whitespace and a leading label makes
    the comparison measure retrieval rather than our punctuation habits.
    """
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def point_needle(point: str) -> str:
    """Return the comparison form of a curated ground-truth point."""
    return _LEADING_LABEL.sub("", normalise(point))


def first_rank_containing(needle: str, chunks: list[str]) -> int | None:
    """Return the 1-based rank of the first chunk that contains ``needle``."""
    target = point_needle(needle)
    if not target:
        return None
    for rank, chunk in enumerate(chunks, start=1):
        if target in normalise(chunk):
            return rank
    return None


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Compare retrieval across top_k values.")
    parser.add_argument("--top-ks", default=",".join(str(k) for k in DEFAULT_TOP_KS))
    args = parser.parse_args(argv)

    top_ks = tuple(int(part) for part in args.top_ks.split(",") if part.strip())
    dataset = json.loads(harness.DATASET_PATH.read_text(encoding="utf-8"))

    lines: list[str] = []

    def emit(line: str = "") -> None:
        lines.append(line)
        print(line)

    emit("=" * 100)
    emit("Retrieval comparison across top_k (real model, throwaway Chroma corpus)")
    emit("=" * 100)
    emit(f"dataset:  {harness.DATASET_PATH}")
    emit(f"questions: {len(dataset)}   top_k values: {', '.join(str(k) for k in top_ks)}")
    emit("")
    emit("A hit only means the text was retrieved. This is not an accuracy metric.")
    emit("")

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        persist_dir = Path(temp_dir) / "chroma"
        store = ChromaVectorStore(
            persist_directory=persist_dir,
            collection_name="rag_topk_compare",
        )
        try:
            chunk_count = harness._ingest_corpus(store, load_pdf_text, embed_text)
            emit(f"corpus chunks: {chunk_count}   len(store): {len(store)}")
            emit("")

            retriever = Retriever(store)
            rows = []

            for entry in dataset:
                question = entry["question"]
                category = category_of(entry)
                expected_ids = list(entry.get("expected_document_ids") or [])
                points = list(entry.get("ground_truth_points") or [])

                per_k = {}
                top_scores = {}
                for k in top_ks:
                    results = retriever.retrieve(question, top_k=k)
                    chunks = [result.text for result in results]
                    docs = [str(r.metadata.get("document_id", "?")) for r in results]
                    ranks = [first_rank_containing(point, chunks) for point in points]
                    present = [rank for rank in ranks if rank is not None]
                    per_k[k] = {
                        "returned": len(results),
                        "doc_hit": bool(expected_ids) and any(d in expected_ids for d in docs[:k]),
                        "points_covered": len(present),
                        "first_point_rank": min(present) if present else None,
                        "top_doc": docs[0] if docs else None,
                    }
                    if results:
                        top_scores[k] = results[0].score

                rows.append(
                    {
                        "id": entry["id"],
                        "category": category,
                        "expected": expected_ids,
                        "points": len(points),
                        "per_k": per_k,
                        "top_score": top_scores.get(top_ks[0], 0.0),
                    }
                )

            emit("1) Per-question coverage")
            header = f"{'id':4} {'category':16} {'points':>6} " + " ".join(
                f"{'k=' + str(k):>16}" for k in top_ks
            )
            emit(header)
            emit("-" * len(header))
            for row in rows:
                cells = []
                for k in top_ks:
                    info = row["per_k"][k]
                    doc = "doc" if info["doc_hit"] else "no-doc"
                    cells.append(f"{doc} {info['points_covered']}/{row['points']}".rjust(16))
                emit(f"{row['id']:4} {row['category']:16} {row['points']:>6} " + " ".join(cells))

            emit("")
            emit("2) Summary per top_k")
            emit(f"{'top_k':>6} {'expected-doc hits':>18} {'all points covered':>20} {'avg returned':>14}")
            for k in top_ks:
                with_doc = [row for row in rows if row["per_k"][k]["doc_hit"]]
                full = [
                    row
                    for row in rows
                    if row["points"] and row["per_k"][k]["points_covered"] == row["points"]
                ]
                avg_returned = sum(row["per_k"][k]["returned"] for row in rows) / len(rows)
                emit(
                    f"{k:>6} {len(with_doc):>18} {len(full):>20} {avg_returned:>14.1f}"
                )

            emit("")
            emit("3) When the first ground-truth point appears (rank at top_k=8)")
            emit(f"{'id':4} {'category':16} {'first point rank':>16} {'top doc':30}")
            for row in rows:
                if not row["points"]:
                    continue
                info = row["per_k"][max(top_ks)]
                rank = info["first_point_rank"]
                emit(
                    f"{row['id']:4} {row['category']:16} "
                    f"{(str(rank) if rank else 'not found'):>16} "
                    f"{str(info['top_doc'])[:30]:30}"
                )

            emit("")
            emit("4) Questions with no answer in the corpus: what still comes back")
            emit(f"{'id':4} {'top score':>10} " + " ".join(f"{'returned@' + str(k):>12}" for k in top_ks))
            negatives = [row for row in rows if row["category"] == "语料缺失"]
            for row in negatives:
                cells = " ".join(f"{row['per_k'][k]['returned']:>12}" for k in top_ks)
                emit(f"{row['id']:4} {row['top_score']:>10.4f} {cells}")

            emit("")
            emit("5) Threshold sweep (top-1 score)")
            positives = [
                row for row in rows if row["category"] in ("完全可答", "部分可答", "部分可答（抽取受限）")
            ]
            emit(
                f"{'cut-off':>8} {'false rejects':>14} {'false accepts':>14}  rejected / accepted"
            )
            for threshold in DEFAULT_THRESHOLDS:
                rejected = [row["id"] for row in positives if row["top_score"] < threshold]
                accepted = [row["id"] for row in negatives if row["top_score"] >= threshold]
                emit(
                    f"{threshold:>8.2f} {len(rejected):>14} {len(accepted):>14}  "
                    f"{','.join(rejected) or '-'} / {','.join(accepted) or '-'}"
                )

            emit("")
            emit("6) Score bands")
            for label, group in (
                ("可答（完全+部分）", positives),
                ("语料缺失", negatives),
            ):
                scores = sorted(row["top_score"] for row in group)
                emit(
                    f"{label:16} n={len(scores):2}  min={scores[0]:.4f}  "
                    f"median={scores[len(scores) // 2]:.4f}  max={scores[-1]:.4f}"
                )

            emit("")
            emit("7) Key-clause probe: does the scope clause reach the model?")
            emit(f"   clause: {SCOPE_CLAUSE}")
            emit(f"{'phrasing':24} {'first rank':>10} " + " ".join(f"{'k=' + str(k):>8}" for k in top_ks))
            for label, probe_question in KEY_CLAUSE_PROBES:
                results = retriever.retrieve(probe_question, top_k=max(top_ks))
                ranks = [
                    rank
                    for rank, result in enumerate(results, start=1)
                    if point_needle(SCOPE_CLAUSE) in normalise(result.text)
                ]
                first = min(ranks) if ranks else None
                cells = " ".join(
                    f"{('yes' if first and first <= k else 'no'):>8}" for k in top_ks
                )
                emit(f"{label:24} {(str(first) if first else 'absent'):>10} {cells}")
            emit("")
            emit("   Some curated points are review statements rather than verbatim text")
            emit("   (q15, q16, q22, and the summary half of q8/q18), so they can never")
            emit("   match a chunk. Coverage above is only meaningful for verbatim points.")
        finally:
            store.close()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print()
    print(f"Report written to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
