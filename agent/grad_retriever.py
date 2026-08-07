"""
D3 — 研究生检索模块: 语义搜索 + 元数据过滤 + 项目详情。

查询 ChromaDB `grad_programs` collection，支持按国家、学校、学位、
专业方向、信息字段等维度精确过滤，结合向量语义检索返回匹配项目。
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Optional

import chromadb
from sentence_transformers import SentenceTransformer

from .config import (
    CHROMA_PATH,
    EMBEDDING_MODEL,
    RETRIEVAL_TOP_K,
    SIMILARITY_THRESHOLD,
)

logger = logging.getLogger(__name__)

GRAD_COLLECTION = "grad_programs"
GRAD_SIMILARITY_THRESHOLD = 0.02  # grad 数据当前为测试集，阈值放低

# 字段 key → 中文标签
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

FIELD_LABEL_TO_KEY = {v: k for k, v in FIELD_LABELS.items()}


class GradProgramRetriever:
    """研究生项目检索引擎。

    基于 ChromaDB `grad_programs` collection 提供:
      - 语义搜索 (向量 + 元数据过滤)
      - 按学校/字段/方向精确查询
      - 项目详情 + 多项目对比
    """

    def __init__(self):
        self._embedding_model: Optional[SentenceTransformer] = None
        self._chroma_client: Optional[chromadb.PersistentClient] = None
        self._collection = None
        self._available = True  # collection 是否存在

    # ── 懒加载资源 ───────────────────────────────────────────

    @property
    def embedding_model(self) -> SentenceTransformer:
        if self._embedding_model is None:
            logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
            self._embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        return self._embedding_model

    @property
    def collection(self):
        if self._collection is None:
            self._chroma_client = chromadb.PersistentClient(
                path=CHROMA_PATH,
                settings=chromadb.Settings(anonymized_telemetry=False),
            )
            try:
                self._collection = self._chroma_client.get_collection(GRAD_COLLECTION)
            except Exception:
                logger.warning("Collection '%s' not found", GRAD_COLLECTION)
                self._available = False
                self._collection = None
        return self._collection

    def _ensure_collection(self):
        if not self._available or self.collection is None:
            return False
        return True

    # ── where 子句构建 ──────────────────────────────────────

    def _build_where(
        self,
        country: Optional[str] = None,
        school: Optional[str] = None,
        degree: Optional[str] = None,
        major_direction: Optional[str] = None,
        field: Optional[str] = None,
        chunk_type: Optional[str] = None,
    ) -> Optional[dict]:
        """构建 ChromaDB where 过滤条件。"""
        parts = []
        if country:
            parts.append({"country": {"$eq": country}})
        if school:
            parts.append({"school": {"$eq": school}})
        if degree:
            parts.append({"degree": {"$eq": degree}})
        if major_direction:
            parts.append({"major_direction": {"$eq": major_direction}})
        if field:
            parts.append({"field": {"$eq": field}})
        if chunk_type:
            parts.append({"chunk_type": {"$eq": chunk_type}})

        if not parts:
            return None
        if len(parts) == 1:
            return parts[0]
        return {"$and": parts}

    # ── 结果聚合 ────────────────────────────────────────────

    def _dedup_by_program(self, results: list[dict]) -> list[dict]:
        """按 (school, program_name) 去重，保留最高相似度的 chunk。"""
        seen: dict[str, dict] = {}
        for r in results:
            meta = r.get("metadata", {})
            key = f"{meta.get('school', '')}|{meta.get('program_name', '')}"
            if key not in seen or r.get("similarity", 0) > seen[key].get("similarity", 0):
                seen[key] = r
        # 按相似度降序
        return sorted(seen.values(), key=lambda r: r.get("similarity", 0), reverse=True)

    # ── 主搜索 ──────────────────────────────────────────────

    def search_programs(
        self,
        query: str,
        top_k: int = RETRIEVAL_TOP_K,
        country: Optional[str] = None,
        school: Optional[str] = None,
        degree: Optional[str] = None,
        major_direction: Optional[str] = None,
        field: Optional[str] = None,
        dedup: bool = True,
    ) -> dict:
        """语义搜索研究生项目。

        默认检索 program_full chunk (覆盖面最完整)，有 field 参数时
        检索 field chunk 做精确字段匹配。

        Args:
            query: 搜索查询文本
            top_k: 返回项目数
            country: 国家过滤 (UK / HK / SG)
            school: 学校过滤
            degree: 学位过滤 (MSc / MA / ...)
            major_direction: 专业方向过滤 (Analytics / Finance / ...)
            field: 字段过滤 (application_deadlines 等)
            dedup: 是否按项目去重
        """
        if not self._ensure_collection():
            return {"error": "grad_programs collection not found", "total_hits": 0, "results": []}

        # field 过滤时限定 chunk_type=field，否则不做限定（搜全部 chunk 覆盖面更好）
        where = self._build_where(
            country=country, school=school, degree=degree,
            major_direction=major_direction, field=field,
            chunk_type="field" if field else None,
        )

        # 有过滤条件时扩大召回
        has_filters = any([country, school, degree, major_direction, field])
        fetch_k = max(top_k * 4, 60) if has_filters else max(top_k * 2, 30)

        query_embedding = self.embedding_model.encode(
            [query], normalize_embeddings=True
        ).tolist()

        raw = self.collection.query(
            query_embeddings=query_embedding,
            n_results=fetch_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        results = []
        if raw["ids"] and raw["ids"][0]:
            for i in range(len(raw["ids"][0])):
                distance = raw["distances"][0][i]
                if distance > 1 - GRAD_SIMILARITY_THRESHOLD:
                    continue
                results.append({
                    "id": raw["ids"][0][i],
                    "document": raw["documents"][0][i],
                    "metadata": raw["metadatas"][0][i],
                    "distance": round(distance, 4),
                    "similarity": round(1 - distance, 4),
                })

        if dedup:
            results = self._dedup_by_program(results)

        results = results[:top_k]

        # 统计
        schools = Counter()
        directions = Counter()
        for r in results:
            meta = r.get("metadata", {})
            schools[meta.get("school", "?")] += 1
            directions[meta.get("major_direction", "?")] += 1

        return {
            "query": query,
            "total_hits": len(results),
            "results": results,
            "filters_applied": {
                "country": country, "school": school, "degree": degree,
                "major_direction": major_direction, "field": field,
            },
            "by_school": dict(schools.most_common(10)),
            "by_direction": dict(directions.most_common(10)),
        }

    # ── 按学校检索 ──────────────────────────────────────────

    def search_by_school(self, school: str, top_k: int = 30) -> dict:
        """检索某个学校的所有项目。"""
        return self.search_programs(
            query=f"{school} 研究生项目",
            top_k=top_k,
            school=school,
            dedup=True,
        )

    # ── 按字段检索 ──────────────────────────────────────────

    def search_by_field(
        self,
        query: str,
        field_type: str,
        top_k: int = RETRIEVAL_TOP_K,
        country: Optional[str] = None,
        school: Optional[str] = None,
    ) -> dict:
        """在特定字段中搜索 (如只看"申请截止日期")。

        field_type 支持 snake_case key 或中文标签。
        """
        # 中文标签 → key
        if field_type in FIELD_LABEL_TO_KEY:
            field_key = FIELD_LABEL_TO_KEY[field_type]
        elif field_type in FIELD_LABELS:
            field_key = field_type
        else:
            field_key = field_type  # 尝试直接使用

        return self.search_programs(
            query=query,
            top_k=top_k,
            country=country,
            school=school,
            field=field_key,
            dedup=False,  # 字段级不去重，保留多个 chunk
        )

    # ── 项目详情 ────────────────────────────────────────────

    def get_program_detail(self, school: str, program_name: str) -> Optional[dict]:
        """获取单个项目的所有 chunk (完整信息)。"""
        if not self._ensure_collection():
            return None

        raw = self.collection.get(
            where={"$and": [
                {"school": school},
                {"program_name": program_name},
            ]},
            include=["documents", "metadatas"],
        )

        if not raw["ids"]:
            return None

        chunks = []
        for i in range(len(raw["ids"])):
            meta = raw["metadatas"][i] or {}
            chunks.append({
                "id": raw["ids"][i],
                "field": meta.get("field", ""),
                "field_label": meta.get("field_label", ""),
                "chunk_type": meta.get("chunk_type", ""),
                "content": raw["documents"][i] or "",
                "source_url": meta.get("source_url", ""),
            })

        # 提取项目级元数据
        meta = raw["metadatas"][0] if raw["metadatas"] else {}

        return {
            "school": school,
            "program_name": program_name,
            "degree": meta.get("degree", ""),
            "country": meta.get("country", ""),
            "major_direction": meta.get("major_direction", ""),
            "chunk_count": len(chunks),
            "chunks": chunks,
        }

    # ── 学校列表 ────────────────────────────────────────────

    def list_schools(self) -> dict:
        """列出所有学校及各校项目数。"""
        if not self._ensure_collection():
            return {"error": "grad_programs collection not found", "schools": []}

        # 用 program_full chunk 做统计 (每个项目只有一个 full chunk)
        raw = self.collection.get(
            where={"chunk_type": {"$eq": "program_full"}},
            include=["metadatas"],
        )

        school_programs: dict[str, set] = {}
        school_country: dict[str, str] = {}
        for meta in (raw["metadatas"] or []):
            if not meta:
                continue
            s = meta.get("school", "?")
            p = meta.get("program_name", "")
            c = meta.get("country", "")
            if s not in school_programs:
                school_programs[s] = set()
                school_country[s] = c
            school_programs[s].add(p)

        schools = sorted(
            [
                {
                    "school": s,
                    "country": school_country.get(s, ""),
                    "program_count": len(progs),
                    "programs": sorted(progs),
                }
                for s, progs in school_programs.items()
            ],
            key=lambda x: x["program_count"],
            reverse=True,
        )

        return {
            "total_schools": len(schools),
            "total_programs": sum(s["program_count"] for s in schools),
            "schools": schools,
        }

    # ── 多项目对比 ──────────────────────────────────────────

    def compare_programs(self, programs: list[dict]) -> dict:
        """对比多个项目的关键信息。

        Args:
            programs: [{"school": "HKU", "program_name": "BA"}, ...]

        Returns:
            每个项目的核心字段摘要 + 差异对比
        """
        if not self._ensure_collection():
            return {"error": "grad_programs collection not found", "comparisons": []}

        compare_fields = [
            "application_deadlines",
            "academic_requirements",
            "english_proficiency_requirements",
            "gre_gmat_requirements",
            "cost_of_attendance",
            "financial_aid",
            "program_overview",
        ]

        comparisons = []
        for prog in programs:
            school = prog.get("school", "")
            program_name = prog.get("program_name", "")
            detail = self.get_program_detail(school, program_name)
            if not detail:
                comparisons.append({
                    "school": school,
                    "program_name": program_name,
                    "error": "not found",
                })
                continue

            # 提取对比字段
            fields = {}
            for chunk in detail["chunks"]:
                fk = chunk.get("field", "")
                if fk in compare_fields:
                    fields[fk] = {
                        "label": chunk.get("field_label", ""),
                        "preview": chunk.get("content", "")[:300],
                        "source_url": chunk.get("source_url", ""),
                    }

            comparisons.append({
                "school": detail["school"],
                "program_name": detail["program_name"],
                "degree": detail["degree"],
                "country": detail["country"],
                "major_direction": detail["major_direction"],
                "fields": fields,
            })

        return {
            "compared_count": len(comparisons),
            "comparisons": comparisons,
        }

    # ── 元数据枚举值 ─────────────────────────────────────────

    def list_filter_options(self) -> dict:
        """返回所有可用的过滤选项 (国家/学校/学位/方向/字段)。"""
        if not self._ensure_collection():
            return {"error": "grad_programs collection not found"}

        raw = self.collection.get(
            where={"chunk_type": {"$eq": "program_full"}},
            include=["metadatas"],
        )

        countries = set()
        schools = set()
        degrees = set()
        directions = set()

        for meta in (raw["metadatas"] or []):
            if not meta:
                continue
            if meta.get("country"):
                countries.add(meta["country"])
            if meta.get("school"):
                schools.add(meta["school"])
            if meta.get("degree"):
                degrees.add(meta["degree"])
            if meta.get("major_direction"):
                directions.add(meta["major_direction"])

        return {
            "countries": sorted(countries),
            "schools": sorted(schools),
            "degrees": sorted(degrees),
            "major_directions": sorted(directions),
            "fields": [
                {"key": k, "label": v}
                for k, v in FIELD_LABELS.items()
            ],
        }
