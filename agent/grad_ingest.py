"""
D2 — 研究生数据入库: ChromaDB collection + embedding + 元数据索引。

将 grad_programs_enriched.json 中每个项目生成为多粒度 chunk：
  1. 字段级 chunk — 每个非空字段独立 chunk，便于精确检索
  2. 全项目 chunk — 聚合所有字段为一个全文 chunk，便于整体匹配
  3. 长字段拆分 — 超长字段 (>800字) 按段落拆分为子 chunk

写入 ChromaDB collection `grad_programs`，附带元数据便于结构化过滤检索。
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import Counter
from pathlib import Path
from typing import Optional

import chromadb
from sentence_transformers import SentenceTransformer

from .config import (
    CHROMA_PATH,
    EMBEDDING_MODEL,
)

logger = logging.getLogger(__name__)

GRAD_COLLECTION = "grad_programs"

# 字段中文标签，用于构建可读 chunk 标题
FIELD_LABELS = {
    "application_materials": "申请材料",
    "interview_requirements": "面试要求",
    "application_deadlines": "申请截止日期",
    "academic_requirements": "学术要求",
    "gre_gmat_requirements": "GRE/GMAT要求",
    "english_proficiency_requirements": "语言要求",
    "program_overview": "项目概述",
    "curriculum": "课程设置",
    "cost_of_attendance": "费用",
    "financial_aid": "奖学金/资助",
    "multiple_applications": "多项目申请政策",
    "deferral_admission_policy": "延期入学政策",
    "conditional_admission_policy": "条件录取政策",
}

# 字段排序 (申请相关在前，课程费用在中，政策在后)
FIELD_ORDER = list(FIELD_LABELS.keys())

# 长字段拆分阈值 (字符数)
LONG_FIELD_THRESHOLD = 800
# 长字段拆分段最大长度
CHUNK_MAX_CHARS = 600
# 段间重叠字符数
CHUNK_OVERLAP = 100


def _build_chunk_title(school: str, program_name: str, field_key: str,
                       part: Optional[int] = None) -> str:
    label = FIELD_LABELS.get(field_key, field_key)
    title = f"{school} - {program_name} - {label}"
    if part is not None:
        title += f" ({part})"
    return title


def _split_long_text(text: str, max_chars: int = CHUNK_MAX_CHARS,
                     overlap: int = CHUNK_OVERLAP) -> list[str]:
    """将长文本按段落边界拆分为重叠段。"""
    if len(text) <= LONG_FIELD_THRESHOLD:
        return [text]

    # 先按双换行分段
    paragraphs = re.split(r"\n{2,}", text)
    chunks = []
    current = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) + 2 <= max_chars:
            current = (current + "\n\n" + para).strip() if current else para
        else:
            if current:
                chunks.append(current)
            # 如果单段就超长，按句子或固定长度切
            if len(para) > max_chars:
                sentences = re.split(r"(?<=[.!?])\s+", para)
                sub = ""
                for s in sentences:
                    if len(sub) + len(s) <= max_chars:
                        sub = (sub + " " + s).strip() if sub else s
                    else:
                        if sub:
                            chunks.append(sub)
                        sub = s
                if sub:
                    current = sub
                else:
                    current = ""
            else:
                current = para

    if current:
        chunks.append(current)

    # 如果只有一个 chunk 且长度没超太多，不拆分
    if len(chunks) <= 1:
        return [text]

    # 添加段间重叠
    overlapped = []
    for i, chunk in enumerate(chunks):
        if i > 0 and overlap > 0:
            prev_end = chunks[i - 1][-overlap:] if len(chunks[i - 1]) > overlap else chunks[i - 1]
            chunk = prev_end + "\n...\n" + chunk
        overlapped.append(chunk)

    return overlapped if overlapped else [text]


def load_enriched_programs(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def chunk_program(program: dict) -> list[dict]:
    """将单个项目生成为多粒度 chunk。

    生成策略:
      1. 每个非空字段 → 独立 chunk (字段级)
      2. 长字段 (>800字) → 拆分为多个子 chunk
      3. 所有非空字段聚合 → 一个全项目 chunk (program级)

    Returns:
        [{doc_id, document, metadata, chunk_type}]
    """
    chunks = []
    school = program["school"]
    program_name = program["program_name"]
    country = program["country"]
    degree = program["degree"]
    major_direction = program["major_direction"]

    base_meta = {
        "country": country,
        "school": school,
        "program_name": program_name,
        "degree": degree,
        "major_direction": major_direction,
        "source_file": program.get("source_file", ""),
    }

    # ── 1. 字段级 chunk + 长字段拆分 ──
    all_field_contents = []

    for fk in FIELD_ORDER:
        field_entry = program.get(fk, {})
        content = (field_entry.get("content") or "").strip()
        url = (field_entry.get("url") or "").strip()

        if not content or content.lower() in ("not mentioned", "not provided", "n/a"):
            continue

        label = FIELD_LABELS.get(fk, fk)
        all_field_contents.append(f"## {label}\n{content}")

        # 拆分长文本
        sub_texts = _split_long_text(content)

        for i, sub_text in enumerate(sub_texts):
            part = i + 1 if len(sub_texts) > 1 else None
            doc_id = f"{school}-{program_name}-{fk}"
            if part is not None:
                doc_id += f"-p{part}"

            document = _build_chunk_title(school, program_name, fk, part) + "\n\n" + sub_text

            chunks.append({
                "doc_id": doc_id,
                "document": document,
                "metadata": {
                    **base_meta,
                    "field": fk,
                    "field_label": label,
                    "source_url": url,
                    "chunk_type": "field",
                    "part": part or 1,
                },
            })

    # ── 2. 全项目聚合 chunk ──
    if all_field_contents:
        full_text = f"# {school} - {program_name}\n"
        full_text += f"国家: {country} | 学位: {degree} | 方向: {major_direction}\n\n"
        full_text += "\n\n".join(all_field_contents)

        full_doc_id = f"{school}-{program_name}-full"

        chunks.append({
            "doc_id": full_doc_id,
            "document": full_text,
            "metadata": {
                **base_meta,
                "field": "all",
                "field_label": "全部信息",
                "source_url": "",
                "chunk_type": "program_full",
                "part": 0,
            },
        })

    return chunks


def ingest_grad_programs(
    enriched_path: str,
    batch_size: int = 8,
    reset_collection: bool = True,
    use_cpu: bool = False,
) -> dict:
    """主入库流程。

    Args:
        enriched_path: grad_programs_enriched.json 路径
        batch_size: embedding 批大小
        reset_collection: 是否重建 collection
        use_cpu: 强制使用 CPU
        skip_timestamps: 不打印时间戳 (适合嵌套日志)

    Returns:
        {"total_chunks": N, "total_programs": N, "time_elapsed": s}
    """
    start = time.time()

    logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
    if use_cpu:
        model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    else:
        model = SentenceTransformer(EMBEDDING_MODEL)

    logger.info("Loading enriched programs from: %s", enriched_path)
    programs = load_enriched_programs(enriched_path)
    n_programs = len(programs)
    logger.info("Loaded %d programs", n_programs)

    # 为每个程序生成 chunk
    all_chunks: list[dict] = []
    chunks_per_program = {}
    for prog in programs:
        chunks = chunk_program(prog)
        all_chunks.extend(chunks)
        key = f"{prog['school']}-{prog['program_name']}"
        chunks_per_program[key] = len(chunks)

    n_total = len(all_chunks)
    n_field = sum(1 for c in all_chunks if c["metadata"]["chunk_type"] == "field")
    n_full = sum(1 for c in all_chunks if c["metadata"]["chunk_type"] == "program_full")

    logger.info("Generated %d chunks (%d field-level + %d program-full) from %d programs",
                n_total, n_field, n_full, n_programs)

    # ChromaDB client (禁用遥测避免网络延迟)
    client = chromadb.PersistentClient(
        path=CHROMA_PATH,
        settings=chromadb.Settings(
            anonymized_telemetry=False,
        ),
    )

    # 重建 collection
    if reset_collection:
        try:
            client.delete_collection(GRAD_COLLECTION)
            logger.info("Deleted existing collection '%s'", GRAD_COLLECTION)
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=GRAD_COLLECTION,
        metadata={
            "description": "研究生项目数据 — 英港新院校116个项目",
            "total_programs": str(n_programs),
            "embedding_model": EMBEDDING_MODEL,
        },
    )

    # 批量 embedding + upsert (幂等)
    total_batches = (n_total + batch_size - 1) // batch_size
    for i in range(0, n_total, batch_size):
        batch = all_chunks[i:i + batch_size]
        docs = [c["document"] for c in batch]
        ids = [c["doc_id"] for c in batch]
        metadatas = [c["metadata"] for c in batch]

        embeddings = model.encode(
            docs, normalize_embeddings=True
        ).tolist()

        collection.upsert(
            ids=ids,
            documents=docs,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        batch_num = i // batch_size + 1

        if batch_num % 20 == 0 or batch_num == total_batches:
            logger.info("  batch %d/%d done (%d/%d chunks)",
                        batch_num, total_batches,
                        min(i + batch_size, n_total), n_total)

    elapsed = round(time.time() - start, 1)

    result = {
        "total_programs": n_programs,
        "total_chunks": n_total,
        "field_chunks": n_field,
        "program_full_chunks": n_full,
        "collection_name": GRAD_COLLECTION,
        "time_elapsed_seconds": elapsed,
    }

    logger.info("Ingestion complete: %d programs → %d chunks in %.1fs (%.1f chunks/s)",
                result["total_programs"], result["total_chunks"], elapsed,
                n_total / elapsed if elapsed > 0 else 0)

    return result


# ── 验证查询 ────────────────────────────────────────────────

def verify_collection(enriched_path: Optional[str] = None) -> dict:
    """对入库数据执行验证查询。

    Args:
        enriched_path: 如提供，对比 enriched JSON 做完整性检查。
    """
    client = chromadb.PersistentClient(
        path=CHROMA_PATH,
        settings=chromadb.Settings(anonymized_telemetry=False),
    )

    try:
        collection = client.get_collection(GRAD_COLLECTION)
    except Exception:
        return {"error": f"Collection '{GRAD_COLLECTION}' not found"}

    total = collection.count()

    # 获取所有 metadata (分页获取以支持大数据量)
    all_meta = []
    offset = 0
    page_size = 2000
    while True:
        page = collection.get(include=["metadatas"], limit=page_size, offset=offset)
        if not page["metadatas"]:
            break
        all_meta.extend(page["metadatas"])
        offset += page_size

    # 按维度统计
    schools = Counter()
    countries = Counter()
    fields = Counter()
    directions = Counter()
    chunk_types = Counter()
    programs_seen = set()

    for m in all_meta:
        if m:
            schools[m.get("school", "?")] += 1
            countries[m.get("country", "?")] += 1
            fields[m.get("field", "?")] += 1
            directions[m.get("major_direction", "?")] += 1
            chunk_types[m.get("chunk_type", "?")] += 1
            prog_key = f"{m.get('school','')}-{m.get('program_name','')}"
            programs_seen.add(prog_key)

    report = {
        "total_chunks": total,
        "chunk_types": dict(chunk_types),
        "by_country": dict(countries),
        "school_count": len(schools),
        "unique_programs": len(programs_seen),
        "fields": dict(fields),
        "top_schools": dict(schools.most_common(10)),
        "directions": dict(directions.most_common(10)),
    }

    # ── 完整性检查 (对比 enriched JSON) ──
    if enriched_path and os.path.exists(enriched_path):
        enriched = load_enriched_programs(enriched_path)
        expected = set()
        for p in enriched:
            key = f"{p['school']}-{p['program_name']}"
            expected.add(key)

        missing = expected - programs_seen
        extra = programs_seen - expected

        report["completeness"] = {
            "expected_programs": len(expected),
            "found_programs": len(programs_seen),
            "coverage_pct": round(len(programs_seen) / len(expected) * 100, 1),
            "missing_programs": sorted(missing) if missing else [],
            "extra_programs": sorted(extra) if extra else [],
        }

        if missing:
            report["status"] = "incomplete"
            logger.warning("MISSING %d programs in collection!", len(missing))
        else:
            report["status"] = "complete"
            logger.info("All %d programs accounted for in collection.", len(expected))

    # ── 语义搜索验证 ──
    model = SentenceTransformer(EMBEDDING_MODEL)
    test_queries = [
        ("按学校查: HKU", "HKU Business Analytics program"),
        ("按国家查: Singapore", "Singapore graduate programs data science"),
        ("按方向查: Computer Science", "computer science artificial intelligence masters"),
        ("按字段查: 申请截止日期", "application deadline dates 2026"),
        ("按字段查: 语言要求", "IELTS TOEFL English language requirements score"),
    ]

    search_results = {}
    for label, query in test_queries:
        q_emb = model.encode([query], normalize_embeddings=True).tolist()
        raw = collection.query(
            query_embeddings=q_emb,
            n_results=3,
            include=["documents", "metadatas"],
        )
        hits = []
        if raw["ids"] and raw["ids"][0]:
            for i in range(len(raw["ids"][0])):
                hits.append({
                    "id": raw["ids"][0][i],
                    "school": raw["metadatas"][0][i].get("school", ""),
                    "program": raw["metadatas"][0][i].get("program_name", ""),
                    "field": raw["metadatas"][0][i].get("field_label", ""),
                    "chunk_type": raw["metadatas"][0][i].get("chunk_type", ""),
                    "doc_preview": (raw["documents"][0][i] or "")[:120],
                })
        search_results[label] = hits

    report["search_samples"] = search_results

    return report


def get_program_detail(school: str, program_name: str) -> Optional[dict]:
    """获取单个项目的所有 chunk (用于调试)。"""
    client = chromadb.PersistentClient(
        path=CHROMA_PATH,
        settings=chromadb.Settings(anonymized_telemetry=False),
    )
    try:
        collection = client.get_collection(GRAD_COLLECTION)
    except Exception:
        return None

    results = collection.get(
        where={"$and": [
            {"school": school},
            {"program_name": program_name},
        ]},
        include=["documents", "metadatas"],
    )
    if not results["ids"]:
        return None

    return {
        "school": school,
        "program_name": program_name,
        "chunk_count": len(results["ids"]),
        "chunks": [
            {
                "id": results["ids"][i],
                "field": results["metadatas"][i].get("field_label", ""),
                "chunk_type": results["metadatas"][i].get("chunk_type", ""),
                "preview": (results["documents"][i] or "")[:200],
            }
            for i in range(len(results["ids"]))
        ],
    }


# ── CLI ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(description="D2: 研究生数据入库")
    parser.add_argument("--verify-only", action="store_true",
                        help="仅验证已有 collection，不重新入库")
    parser.add_argument("--no-reset", action="store_true",
                        help="不清空已有 collection (upsert 模式)")
    parser.add_argument("--cpu", action="store_true",
                        help="强制使用 CPU (MPS 显存不足时)")
    parser.add_argument("--batch-size", type=int, default=8,
                        help="embedding 批大小 (默认 8)")
    parser.add_argument("--detail", type=str, nargs=2,
                        metavar=("SCHOOL", "PROGRAM"),
                        help="查看指定项目的所有 chunk (用于调试)")
    args = parser.parse_args()

    BASE = Path(__file__).resolve().parent.parent
    enriched_path = str(BASE / "output" / "grad_programs_enriched.json")

    if args.detail:
        detail = get_program_detail(args.detail[0], args.detail[1])
        if detail:
            print(json.dumps(detail, ensure_ascii=False, indent=2))
        else:
            print(f"Program not found: {args.detail[0]} - {args.detail[1]}")
    elif args.verify_only:
        print("=== 验证 grad_programs collection ===\n")
        report = verify_collection(enriched_path=enriched_path)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        if not os.path.exists(enriched_path):
            raise SystemExit(
                f"Enriched data not found: {enriched_path}\n"
                f"Run 'python agent/grad_schema.py' first to generate it."
            )

        result = ingest_grad_programs(
            enriched_path,
            batch_size=args.batch_size,
            reset_collection=not args.no_reset,
            use_cpu=args.cpu,
        )
        print()
        print("=== Ingestion complete ===")
        print(json.dumps(result, ensure_ascii=False, indent=2))

        print()
        print("=== Verification ===")
        report = verify_collection(enriched_path=enriched_path)
        print(json.dumps(report, ensure_ascii=False, indent=2))
