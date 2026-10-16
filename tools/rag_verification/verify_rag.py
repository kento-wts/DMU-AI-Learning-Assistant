"""Read-only RAG verification harness (Phase 1 diagnostics + Phase 2 ablation).

Every experiment writes to a throwaway temporary Chroma directory. The
repository's own index (``data/chroma``) is never opened or modified.

Run from the repository root:

    python tools/rag_verification/verify_rag.py

Experiments
-----------
E1  real-model ingest of every knowledge PDF
E2  idempotency: ingest the whole corpus twice into one collection
E3  Kangxi-radical damage measurement (the 2026 list PDF)
E4  diagnostic retrieval for the curated evaluation query
E5  year-bearing query: does top-k mix the 2025 and 2026 lists?
E6  empty / whitespace-only document handling
E7  metadata filtering: whole-corpus search vs. filtered search
E8  source provenance in retrieved results and in the built prompt
E9  before/after ablation: same corpus, same query, with and without the
    Phase 2 compatibility-character repair
"""

from __future__ import annotations

import json
import sys
import tempfile
import unicodedata
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.knowledge.chroma_store import ChromaRecord, ChromaVectorStore  # noqa: E402
from backend.knowledge.chunker import chunk_text  # noqa: E402
from backend.knowledge.embedding import cosine_similarity, embed_text  # noqa: E402
from backend.knowledge.ingest import ingest_pdf_to_store  # noqa: E402
from backend.knowledge.pdf_loader import load_pdf_text  # noqa: E402
from backend.knowledge.prompt_builder import build_rag_prompt  # noqa: E402
from backend.knowledge.retriever import Retriever  # noqa: E402

DOCUMENTS_DIR = REPO_ROOT / "backend" / "knowledge" / "documents"
DATASET_PATH = REPO_ROOT / "backend" / "knowledge" / "evaluation_dataset.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "verification-report.txt"

# Metadata read out of the document text. ``year`` is the year the document
# belongs to; the document's own issue date is recorded in INVENTORY.md.
DOCUMENT_METADATA: dict[str, dict[str, object]] = {
    "附件1.《大连海事大学本科生创新创业竞赛列表(2026年)》.pdf": {
        "year": 2026,
        "document_type": "竞赛列表",
        "document_id": "dlmu-competition-list-2026",
    },
    "附件.《大连海事大学本科生创新创业竞赛列表(2025年)》.pdf": {
        "year": 2025,
        "document_type": "竞赛列表",
        "document_id": "dlmu-competition-list-2025",
    },
    "大连海事大学办公室关于印发《大连海事大学大学生创新创业竞赛管理办法》的通知.pdf": {
        "year": 2023,
        "document_type": "管理办法",
        "document_id": "dlmu-innovation-competition-rules-2023",
    },
    "大连海事大学大学生科技创新奖励办法（正文）.pdf": {
        "year": 2024,
        "document_type": "奖励办法",
        "document_id": "dlmu-innovation-award-2024",
    },
    "大连海事大学党政办公室关于印发《大连海事大学推荐优秀应届本科毕业生免试攻读硕士研究生办法》的通知.pdf": {
        "year": 2025,
        "document_type": "推免办法",
        "document_id": "dlmu-postgraduate-recommendation-2025",
    },
    "大连海事大学党政办公室关于印发《大连海事大学非航海类专业本科生学籍管理规定》的通知.pdf": {
        "year": 2021,
        "document_type": "学籍管理规定",
        "document_id": "dlmu-status-rules-2021",
    },
    "大连海事大学本科生奖学金评定办法.pdf": {
        "year": 2023,
        "document_type": "奖学金评定办法",
        "document_id": "dlmu-scholarship-2023",
    },
    "大连海事大学学生违纪处分办法.pdf": {
        "year": 2022,
        "document_type": "违纪处分办法",
        "document_id": "dlmu-discipline-2022",
    },
    "2025-2中队本科生综合素质测评实施细则.pdf": {
        "year": 2025,
        "document_type": "综合素质测评实施细则",
        "document_id": "dlmu-xinxikexue-2025-2-assessment",
    },
    "大连海事大学学生离校请假单.pdf": {
        "year": 2025,
        "document_type": "表单",
        "document_id": "dlmu-leave-form",
    },
}

_QUERY = "我是大连海事大学软件工程专业（隶属信息科学技术学院）的一名大二学生，我想参加学院承办的相关创新创业的A类竞赛，你能给我推荐一些吗？"

# Canonical CJK characters observed in the 2026 PDF as Kangxi-radical
# compatibility forms. Used only to rebuild a probe string in the same
# damaged form the extractor produced.
_KANGXI_FORMS: dict[str, str] = {
    "大": "\u2f24", "工": "\u2f2f", "生": "\u2f63", "高": "\u2fbc",
    "人": "\u2f08", "用": "\u2f64", "力": "\u2f12", "心": "\u2f3c",
    "文": "\u2f42", "子": "\u2f26", "网": "\u2f79", "行": "\u2f8f",
    "土": "\u2f1f", "金": "\u2fa6", "目": "\u2f6c", "自": "\u2f83",
    "比": "\u2f50", "木": "\u2f4a", "日": "\u2f47", "无": "\u2f46",
}


class Report:
    """Collect human-readable findings and mirror them to stdout."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.results: dict[str, object] = {}

    def write(self, line: str = "") -> None:
        self.lines.append(line)
        print(line)

    def section(self, title: str) -> None:
        self.write()
        self.write("=" * 96)
        self.write(title)
        self.write("=" * 96)

    def record(self, key: str, value: object) -> None:
        self.results[key] = value
        self.write(f"EXPERIMENT_RESULT {key} {json.dumps(value, ensure_ascii=False)}")

    def save(self) -> None:
        OUTPUT_PATH.write_text("\n".join(self.lines) + "\n", encoding="utf-8", newline="\n")


def _paragraph(text: str) -> str:
    return "|".join(text.split())


def _to_kangxi(text: str) -> str:
    """Rewrite canonical CJK characters into the Kangxi forms from the PDF."""
    return "".join(_KANGXI_FORMS.get(char, char) for char in text)


def _name_overlap(names: list[str], chunks: list[str]) -> list[str]:
    normalised = [unicodedata.normalize("NFKC", chunk) for chunk in chunks]
    return [
        name
        for name in names
        if unicodedata.normalize("NFKC", name)
        and any(unicodedata.normalize("NFKC", name) in chunk for chunk in normalised)
    ]


def _pdf_paths() -> list[Path]:
    return sorted(DOCUMENTS_DIR.glob("*.pdf"))


def _ingest_corpus(
    store: ChromaVectorStore,
    text_loader,
    embedder,
) -> int:
    """Ingest every PDF using an injected loader and embedder.

    Used to build a pre-fix corpus without modifying the working tree.
    """
    from backend.knowledge.ingest import _build_chunk_id, _hash_text, _resolve_document_id

    total = 0
    for pdf_path in _pdf_paths():
        metadata = dict(DOCUMENT_METADATA[pdf_path.name])
        document_id = _resolve_document_id(str(pdf_path), metadata)
        text = text_loader(str(pdf_path))
        chunks = chunk_text(text)

        records = []
        for index, chunk in enumerate(chunks):
            chunk_hash = _hash_text(chunk)
            records.append(
                ChromaRecord(
                    id=_build_chunk_id(document_id, index, chunk_hash),
                    text=chunk,
                    vector=embedder(chunk),
                    metadata={
                        **metadata,
                        "document_id": document_id,
                        "source": Path(pdf_path).name,
                        "chunk_index": index,
                        "chunk_hash": chunk_hash,
                    },
                )
            )
        store.replace_document(document_id, records)
        total += len(records)
    return total


def _embed_text_raw(text: str) -> list[float]:
    """Pre-fix embedding: no NFKC repair, exactly what the old code did."""
    stripped = text.strip()
    if not stripped:
        return []
    from backend.knowledge.embedding import _get_model, _vector_to_floats

    return _vector_to_floats(list(_get_model().embed([stripped]))[0])


def _load_pdf_text_raw(pdf_path: str) -> str:
    """Pre-fix extraction: keep the carriage-return handling, skip NFKC."""
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    pages = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        stripped = page_text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if stripped:
            pages.append(stripped)
    return "\n\n".join(pages)


def e1_real_ingest(report: Report, persist_dir: Path) -> None:
    """Ingest every knowledge PDF with the real embedding model."""
    report.section("E1  Real-model ingest of the 10 knowledge PDFs (Phase 2 code)")

    store = ChromaVectorStore(persist_directory=persist_dir, collection_name="rag_verify_e1")
    per_document = []
    total = 0

    for pdf_path in _pdf_paths():
        metadata = dict(DOCUMENT_METADATA[pdf_path.name])
        chunk_count = ingest_pdf_to_store(str(pdf_path), metadata, store)
        records = store.get_records({"document_id": metadata["document_id"]})
        text_lengths = [len(record.text) for record in records]
        compatibility = sum(
            sum(1 for char in record.text if unicodedata.normalize("NFKC", char) != char)
            for record in records
        )
        total += chunk_count
        per_document.append(
            {
                "document_id": metadata["document_id"],
                "chunks": chunk_count,
                "max_chunk_chars": max(text_lengths) if text_lengths else 0,
                "chunks_over_1200": sum(1 for n in text_lengths if n > 1200),
                "compatibility_chars": compatibility,
            }
        )

    report.write(f"{'document_id':<44}{'chunks':>7}{'maxlen':>8}{'>1200':>6}{'compat':>8}")
    report.write("-" * 96)
    for entry in per_document:
        report.write(
            f"{entry['document_id']:<44}{entry['chunks']:>7}{entry['max_chunk_chars']:>8}"
            f"{entry['chunks_over_1200']:>6}{entry['compatibility_chars']:>8}"
        )
    report.write("-" * 96)
    all_records = store.get_records()
    report.write(f"total chunks: {total}   len(store): {len(store)}")
    report.write(
        "distinct document_id values: "
        f"{len({record.metadata['document_id'] for record in all_records})}"
    )
    report.write(f"metadata keys: {sorted(all_records[0].metadata)}")
    report.record("e1", {"total_chunks": total, "documents": per_document})
    store.close()


def e2_idempotency(report: Report, persist_dir: Path) -> None:
    """Ingest the whole corpus twice into one collection."""
    report.section("E2  Re-running ingest over the same corpus (duplicate risk)")

    store = ChromaVectorStore(persist_directory=persist_dir, collection_name="rag_verify_e2")
    counts = []
    for run in (1, 2):
        run_total = 0
        for pdf_path in _pdf_paths():
            run_total += ingest_pdf_to_store(
                str(pdf_path), dict(DOCUMENT_METADATA[pdf_path.name]), store
            )
        counts.append(run_total)
        report.write(f"run {run}: chunks reported = {run_total}, len(store) = {len(store)}")

    records = store.get_records()
    duplicate_ids = len(records) - len({record.id for record in records})
    hash_counter = Counter(
        (record.metadata["document_id"], record.metadata["chunk_hash"])
        for record in records
    )
    duplicate_content = sum(count - 1 for count in hash_counter.values() if count > 1)

    passed = counts[0] == counts[1] == len(store) and duplicate_ids == 0 and duplicate_content == 0
    report.write(f"run 1 chunks == run 2 chunks: {counts[0] == counts[1]}")
    report.write(f"duplicate record ids: {duplicate_ids}")
    report.write(f"duplicate (document_id, chunk_hash) pairs: {duplicate_content}")
    report.write(f"PASS: {passed}")
    report.record(
        "e2",
        {
            "counts": counts,
            "store_size": len(store),
            "duplicate_ids": duplicate_ids,
            "duplicate_content": duplicate_content,
            "pass": passed,
        },
    )
    store.close()


def e3_kangxi_damage(report: Report) -> None:
    """Measure the embedding damage caused by Kangxi radicals in the 2026 PDF."""
    report.section("E3  Kangxi-radical damage on the 2026 competition list")

    pdf_path = DOCUMENTS_DIR / "附件1.《大连海事大学本科生创新创业竞赛列表(2026年)》.pdf"
    # Bypass the loader fix to observe the raw extractor output.
    raw_text = _load_pdf_text_raw(str(pdf_path))
    repaired_text = unicodedata.normalize("NFKC", raw_text)
    probe = "中国高校计算机大赛"
    damaged_probe = _to_kangxi(probe)

    report.write(f"raw extracted chars:  {len(raw_text)}")
    report.write(f"NFKC repaired chars:  {len(repaired_text)}")
    report.write(
        f"characters only NFKC repairs: "
        f"{sum(1 for c in raw_text if unicodedata.normalize('NFKC', c) != c)}"
    )
    report.write(f"probe: {probe}")
    report.write(f"probe as the PDF writes it: {damaged_probe}")
    report.write("")

    query_vector = embed_text(_QUERY)
    report.write(f"{'chunk form':<34}{'cosine vs query':>18}")
    report.write("-" * 96)
    rows = []
    # The pre-fix pipeline embedded the extracted chunk text verbatim.
    compare_forms = (
        ("title, pre-fix embedding", _embed_text_raw(damaged_probe)),
        ("title, Phase 2 embedding", embed_text(damaged_probe)),
        ("title, canonical text", embed_text(probe)),
        ("first 400 chars, pre-fix", _embed_text_raw(raw_text[:400])),
        ("first 400 chars, Phase 2", embed_text(raw_text[:400])),
    )
    for label, vector in compare_forms:
        score = cosine_similarity(query_vector, vector)
        rows.append({"form": label, "cosine": round(score, 6)})
        report.write(f"{label:<34}{score:>18.6f}")

    report.write("")
    report.write(
        "The extracted chunk text and the canonical title are different strings "
        "before the fix, so the chunk lands at a different point in vector space "
        "than the same words typed in a query. Phase 2 normalises both sides."
    )
    report.write(
        "cosine(pre-fix vector of the damaged title, Phase 2 vector of the "
        f"canonical title) = {cosine_similarity(_embed_text_raw(damaged_probe), embed_text(probe)):.6f}"
    )

    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    ground_truth = dataset[0]["relevant_competitions"]
    report.write("")
    report.write("Curated ground-truth names inside the 2026 PDF text:")
    presence = {}
    for name in ground_truth:
        presence[name] = {
            "as_extracted": name in raw_text,
            "nfkc_repaired": name in repaired_text,
        }
        report.write(
            f"  {name:<32} as extracted: {name in raw_text!s:<6} "
            f"NFKC repaired: {name in repaired_text}"
        )

    report.record(
        "e3",
        {
            "rows": rows,
            "raw_chars": len(raw_text),
            "repaired_chars": len(repaired_text),
            "name_presence": presence,
        },
    )


def e4_dataset_retrieval(report: Report, persist_dir: Path, collection: str, label: str) -> None:
    """Run the curated evaluation query against one corpus."""
    report.section(f"E4  Curated evaluation query against: {label}")

    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    entry = dataset[0]
    ground_truth = entry["relevant_competitions"]

    corpus = ChromaVectorStore(persist_directory=persist_dir, collection_name=collection)
    retriever = Retriever(corpus)

    report.write(f"collection size: {len(corpus)}")
    report.write("")

    summary = {}
    for top_k in (3, 5, 10):
        results = retriever.retrieve(entry["question"], top_k=top_k)
        # Ground-truth matching is done on NFKC-normalised text for *both*
        # corpora, otherwise the pre-fix corpus would never match a name.
        matched = _name_overlap(ground_truth, [result.text for result in results])
        summary[str(top_k)] = {
            "returned": len(results),
            "matched": matched,
            "matched_count": len(matched),
            "sources": dict(Counter(result.metadata.get("source") for result in results)),
        }
        report.write(f"--- top_k = {top_k} ---")
        for rank, result in enumerate(results, start=1):
            report.write(
                f"  #{rank} score={result.score:.4f} "
                f"source={result.metadata.get('source')} "
                f"year={result.metadata.get('year')} "
                f"chunk_index={result.metadata.get('chunk_index')}"
            )
            report.write(f"       {_paragraph(result.text[:100])}")
        report.write(
            f"  ground-truth names found by text overlap: {len(matched)}/{len(ground_truth)} "
            f"{matched}"
        )
        report.write("")

    report.record("e4_" + collection, summary)
    corpus.close()


def e5_year_mix(report: Report, persist_dir: Path) -> None:
    """Check whether a year-scoped query returns the other year's list."""
    report.section("E5  Year-scoped query: does top-k mix the 2025 and 2026 lists?")

    store = ChromaVectorStore(persist_directory=persist_dir, collection_name="rag_verify_e1")
    retriever = Retriever(store)
    query = "2026年大连海事大学本科生有哪些创新创业竞赛？"

    report.write(f"query: {query}")
    report.write("")
    unfiltered = {}
    for top_k in (3, 5, 10):
        results = retriever.retrieve(query, top_k=top_k)
        sources = Counter(result.metadata.get("source") for result in results)
        unfiltered[str(top_k)] = dict(sources)
        report.write(f"top_k={top_k}: {dict(sources)}")
        for rank, result in enumerate(results[:3], start=1):
            report.write(
                f"  #{rank} score={result.score:.4f} source={result.metadata.get('source')}"
            )
        report.write("")

    filtered_2026 = retriever.retrieve(query, top_k=10, metadata_filter={"year": 2026})
    report.write("metadata_filter={'year': 2026}:")
    report.write(
        f"  returned {len(filtered_2026)} chunks, "
        f"sources={dict(Counter(r.metadata.get('source') for r in filtered_2026))}"
    )
    filtered_2025 = retriever.retrieve(
        query, top_k=10, metadata_filter={"document_id": "dlmu-competition-list-2025"}
    )
    report.write("metadata_filter={'document_id': 'dlmu-competition-list-2025'}:")
    report.write(
        f"  returned {len(filtered_2025)} chunks, "
        f"sources={dict(Counter(r.metadata.get('source') for r in filtered_2025))}"
    )
    report.write("")
    report.write(
        "Finding: the running service calls retrieve() with no metadata_filter "
        "(backend/main.py), so an explicit year in the question does not restrict "
        "the candidate set."
    )
    report.record(
        "e5",
        {
            "unfiltered_sources": unfiltered,
            "filtered_year_2026": len(filtered_2026),
            "filtered_2025_document": len(filtered_2025),
        },
    )
    store.close()


def e6_empty_document(report: Report, persist_dir: Path) -> None:
    """Empty/whitespace source behavior through the storage layer."""
    report.section("E6  Empty and whitespace-only content")

    store = ChromaVectorStore(persist_directory=persist_dir, collection_name="rag_verify_e6")
    store.add("先有的内容", [1.0, 0.0], {"document_id": "doc-x"})
    before = len(store)
    store.replace_document("doc-x", [])
    report.write(f"replace_document(id, []) removed existing records: {before} -> {len(store)}")

    outcomes = []
    for label, records in (
        ("empty text", [ChromaRecord(id="e1", text="", vector=[1.0, 0.0], metadata={})]),
        ("whitespace text", [ChromaRecord(id="e2", text="   \n ", vector=[1.0, 0.0], metadata={})]),
        ("empty vector", [ChromaRecord(id="e3", text="x", vector=[], metadata={})]),
        ("zero vector", [ChromaRecord(id="e4", text="x", vector=[0.0, 0.0], metadata={})]),
    ):
        try:
            store.upsert_many(records)
            outcomes.append(f"{label}: accepted silently (defect)")
        except Exception as exc:  # noqa: BLE001
            outcomes.append(f"{label}: rejected with {type(exc).__name__}")

    for line in outcomes:
        report.write(f"  {line}")

    report.write(f"  chunk_text(whitespace only) -> {chunk_text(chr(10) * 2 + '  ' + chr(10))!r}")
    report.write(f"  embed_text(whitespace only) -> {embed_text('   ')}")
    report.write(f"  store size after invalid writes: {len(store)}")
    report.record("e6", {"outcomes": outcomes, "store_size": len(store)})
    store.close()


def e7_metadata_filter(report: Report, persist_dir: Path) -> None:
    """Metadata filter behavior on the real corpus."""
    report.section("E7  Metadata filtering on the real corpus")

    store = ChromaVectorStore(persist_directory=persist_dir, collection_name="rag_verify_e1")
    retriever = Retriever(store)
    query = "软件工程专业大二学生可以参加哪些A类创新创业竞赛？"

    unfiltered = retriever.retrieve(query, top_k=10)
    report.write(f"no filter             -> {len(unfiltered)} chunks")
    report.write(f"  sources: {dict(Counter(r.metadata.get('source') for r in unfiltered))}")
    report.write(f"  years:   {dict(Counter(r.metadata.get('year') for r in unfiltered))}")

    filtered = retriever.retrieve(query, top_k=10, metadata_filter={"document_type": "竞赛列表"})
    report.write(f"document_type=竞赛列表  -> {len(filtered)} chunks")
    report.write(f"  sources: {dict(Counter(r.metadata.get('source') for r in filtered))}")

    filtered_2026 = retriever.retrieve(query, top_k=10, metadata_filter={"year": 2026})
    report.write(f"year=2026             -> {len(filtered_2026)} chunks")
    report.write(f"  sources: {dict(Counter(r.metadata.get('source') for r in filtered_2026))}")

    no_match = retriever.retrieve(query, top_k=10, metadata_filter={"year": 1999})
    report.write(f"year=1999 (no match)  -> {len(no_match)} chunks (expected 0)")

    oversized = retriever.retrieve(
        query, top_k=50, metadata_filter={"document_id": "dlmu-leave-form"}
    )
    report.write(f"document_id=请假单, top_k=50 -> {len(oversized)} chunks (collection has {len(store)})")

    report.record(
        "e7",
        {
            "unfiltered": len(unfiltered),
            "filtered_document_type": len(filtered),
            "filtered_year_2026": len(filtered_2026),
            "no_match": len(no_match),
            "oversized_top_k": len(oversized),
        },
    )
    store.close()


def e8_provenance(report: Report, persist_dir: Path) -> None:
    """Where do source and date information survive?"""
    report.section("E8  Provenance: source and date carrying into the prompt")

    store = ChromaVectorStore(persist_directory=persist_dir, collection_name="rag_verify_e1")
    retriever = Retriever(store)
    query = "推荐优秀应届本科毕业生免试攻读硕士研究生的办法是什么？"
    results = retriever.retrieve(query, top_k=3)

    report.write("SearchResult.metadata of the top chunk:")
    report.write(json.dumps(results[0].metadata, ensure_ascii=False, indent=2))
    report.write("")

    prompt = build_rag_prompt(query, results)
    report.write("Built RAG prompt (first 900 characters):")
    report.write(prompt[:900])
    report.write("...")
    report.write("")

    source = str(results[0].metadata["source"])
    report.write(f"prompt contains the source filename: {source in prompt}")
    report.write(f"prompt contains '来源文件':            {'来源文件' in prompt}")
    report.write(f"prompt contains a year field:         {'适用年份' in prompt}")
    report.write(f"prompt contains 'chunk_hash':         {'chunk_hash' in prompt}")
    report.record(
        "e8",
        {
            "metadata_keys": sorted(results[0].metadata),
            "source_in_prompt": source in prompt,
            "source_label_in_prompt": "来源文件" in prompt,
            "year_label_in_prompt": "适用年份" in prompt,
            "chunk_hash_in_prompt": "chunk_hash" in prompt,
            "prompt_chars": len(prompt),
        },
    )
    store.close()


def e9_ablation(report: Report, persist_dir: Path) -> None:
    """Before/after: identical corpus and query, only the repair differs."""
    report.section("E9  Ablation - pre-fix vs Phase 2 corpus on the same query")

    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    entry = dataset[0]
    ground_truth = entry["relevant_competitions"]

    pre_store = ChromaVectorStore(
        persist_directory=persist_dir, collection_name="rag_verify_prefix"
    )
    pre_total = _ingest_corpus(
        pre_store, _load_pdf_text_raw, _embed_text_raw
    )
    report.write(f"pre-fix corpus: {pre_total} chunks, len(store)={len(pre_store)}")

    fixed_store = ChromaVectorStore(
        persist_directory=persist_dir, collection_name="rag_verify_e1"
    )
    report.write(f"Phase 2 corpus: len(store)={len(fixed_store)}")
    report.write("")

    report.write(f"{'top_k':<8}{'pre-fix matched':>18}{'Phase 2 matched':>18}")
    report.write("-" * 96)

    ablation = {}
    for top_k in (3, 5, 10):
        pre_hits = _name_overlap(
            ground_truth,
            [result.text for result in pre_store.search(_embed_text_raw(entry["question"]), top_k=top_k)],
        )
        fixed_hits = _name_overlap(
            ground_truth,
            [result.text for result in fixed_store.search(embed_text(entry["question"]), top_k=top_k)],
        )
        ablation[str(top_k)] = {
            "prefix_matched": len(pre_hits),
            "fixed_matched": len(fixed_hits),
            "prefix_names": pre_hits,
            "fixed_names": fixed_hits,
        }
        report.write(f"{top_k:<8}{len(pre_hits):>18}{len(fixed_hits):>18}")

    report.write("")
    report.write(
        "Both corpora are scored with a ground-truth text-overlap check that "
        "NFKC-normalises the chunk text, so the only difference measured here "
        "is whether retrieval surfaced the chunk at all."
    )
    report.record("e9", ablation)
    pre_store.close()
    fixed_store.close()


def e10_score_effect(report: Report) -> None:
    """Measure exactly how much the repair moves the affected 2026 chunks.

    Both sides start from the same raw extractor output. The pre-fix side
    embeds the extracted (radical-bearing) text; the Phase 2 side normalises
    first. Nothing is read out of a store, so the comparison is exact.
    """
    report.section("E10  Per-chunk score effect of the repair (2026 list only)")

    pdf_path = DOCUMENTS_DIR / "附件1.《大连海事大学本科生创新创业竞赛列表(2026年)》.pdf"
    raw_text = _load_pdf_text_raw(str(pdf_path))
    fixed_text = unicodedata.normalize("NFKC", raw_text)

    raw_chunks = chunk_text(raw_text)
    fixed_chunks = chunk_text(fixed_text)

    report.write(f"raw chunks: {len(raw_chunks)}   Phase 2 chunks: {len(fixed_chunks)}")
    if len(raw_chunks) != len(fixed_chunks):
        report.write(
            "WARNING: chunk counts differ, so per-index comparison is not meaningful"
        )

    query = "中国大学生计算机设计大赛是什么级别的竞赛？"
    query_vector = embed_text(query)
    report.write(f"query: {query}")
    report.write("")
    report.write(
        f"{'chunk':>6}{'pre-fix cos':>14}{'Phase 2 cos':>14}{'delta':>10}"
        f"{'radicals':>10}   text head"
    )
    report.write("-" * 104)

    deltas = []
    for index, (raw_chunk, fixed_chunk) in enumerate(zip(raw_chunks, fixed_chunks)):
        score_before = cosine_similarity(query_vector, _embed_text_raw(raw_chunk))
        score_after = cosine_similarity(query_vector, embed_text(raw_chunk))
        radical_count = sum(
            1 for char in raw_chunk if unicodedata.normalize("NFKC", char) != char
        )
        deltas.append(
            {
                "chunk_index": index,
                "radicals": radical_count,
                "before": round(score_before, 6),
                "after": round(score_after, 6),
                "delta": round(score_after - score_before, 6),
            }
        )
        report.write(
            f"{index:>6}{score_before:>14.6f}{score_after:>14.6f}"
            f"{score_after - score_before:>10.6f}{radical_count:>10}   "
            f"{_paragraph(fixed_chunk[:34])}"
        )

    improved = [d for d in deltas if d["delta"] > 1e-9]
    unchanged = [d for d in deltas if abs(d["delta"]) <= 1e-9]
    report.write("")
    report.write(f"chunks whose score improved: {len(improved)} / {len(deltas)}")
    report.write(f"chunks whose score unchanged: {len(unchanged)} / {len(deltas)}")
    if deltas:
        report.write(f"largest improvement: {max(d['delta'] for d in deltas):+.6f}")
        report.write(f"largest regression:  {min(d['delta'] for d in deltas):+.6f}")
    report.write("")
    report.write(
        "Interpretation: only chunks that actually contain compatibility characters "
        "move. This is a bounded correction of a text-extraction defect, not a "
        "general retrieval-quality improvement."
    )
    report.record("e10", deltas)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    report = Report()
    report.write("DMU AI Learning Assistant - RAG verification harness")
    report.write(f"repository root: {REPO_ROOT}")
    report.write(f"documents:       {len(_pdf_paths())} PDF files")

    with tempfile.TemporaryDirectory(
        prefix="rag-verify-", ignore_cleanup_errors=True
    ) as temp_dir:
        persist_dir = Path(temp_dir) / "chroma"
        report.write(f"throwaway Chroma dir (the repo index is never opened): {persist_dir}")

        steps = (
            lambda: e1_real_ingest(report, persist_dir),
            lambda: e2_idempotency(report, persist_dir),
            lambda: e3_kangxi_damage(report),
            lambda: e4_dataset_retrieval(report, persist_dir, "rag_verify_e1", "Phase 2 code"),
            lambda: e5_year_mix(report, persist_dir),
            lambda: e6_empty_document(report, persist_dir),
            lambda: e7_metadata_filter(report, persist_dir),
            lambda: e8_provenance(report, persist_dir),
            lambda: e9_ablation(report, persist_dir),
            lambda: e10_score_effect(report),
        )

        for step in steps:
            try:
                step()
            except Exception as exc:  # noqa: BLE001
                report.write("")
                report.write(f"HARNESS STEP ABORTED: {type(exc).__name__}: {exc}")
                import traceback

                report.write(traceback.format_exc())

    report.section("DONE")
    report.save()
    print(f"\nReport written to {OUTPUT_PATH}")

    # Keep the committed reference copy in sync as valid UTF-8 when the tool is
    # run from the repository checkout.
    reference = OUTPUT_PATH.parent / "reference"
    if reference.is_dir():
        (reference / "baseline-verification-report.txt").write_text(
            "\n".join(report.lines) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"Reference copy updated: {reference / 'baseline-verification-report.txt'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
