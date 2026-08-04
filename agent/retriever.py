import logging
from typing import Optional

import chromadb
from sentence_transformers import SentenceTransformer

from .config import (
    CHROMA_PATH,
    CHROMA_COLLECTION,
    EMBEDDING_MODEL,
    RETRIEVAL_TOP_K,
    RETRIEVAL_TOP_K_LARGE,
    SIMILARITY_THRESHOLD,
    FUSION_VECTOR_WEIGHT,
    FUSION_RULE_WEIGHT,
)

logger = logging.getLogger(__name__)

# doc_type 权重：在规则评分中的优先级
DOC_TYPE_RULE_WEIGHT = {
    "录取结果": 0.35,
    "顾问笔记": 0.30,
    "school_profile": 0.25,
    "标化资料": 0.15,
    "招生简章": 0.15,
    "课程介绍": 0.05,
    "叙述文章": 0.05,
    "其他": 0.05,
}


class Retriever:
    def __init__(self):
        self._embedding_model: Optional[SentenceTransformer] = None
        self._chroma_client: Optional[chromadb.PersistentClient] = None
        self._collection = None

    @property
    def embedding_model(self):
        if self._embedding_model is None:
            logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
            self._embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        return self._embedding_model

    @property
    def collection(self):
        if self._collection is None:
            self._chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
            self._collection = self._chroma_client.get_collection(CHROMA_COLLECTION)
        return self._collection

    # ── query 构建 ───────────────────────────────────────────

    def _build_case_query(self, profile: dict) -> str:
        parts = ["学生画像:"]

        curriculum = profile.get("curriculum")
        if curriculum:
            parts.append(f"{curriculum}课程体系,")

        gpa = profile.get("gpa")
        if gpa:
            parts.append(f"GPA {gpa},")

        toefl = profile.get("toefl")
        if toefl:
            parts.append(f"TOEFL {toefl},")

        ielts = profile.get("ielts")
        if ielts:
            parts.append(f"IELTS {ielts},")

        sat = profile.get("sat")
        if sat:
            parts.append(f"SAT {sat},")

        act = profile.get("act")
        if act:
            parts.append(f"ACT {act},")

        major = profile.get("major_interest")
        if major:
            parts.append(f"专业意向 {', '.join(major)},")

        country = profile.get("country_pref")
        if country:
            parts.append(f"意向国家 {', '.join(country)},")

        parts.append("寻找相似录取案例和匹配学校")

        query = " ".join(parts)
        logger.debug("Built case query: %s", query)
        return query

    # ── 去重 ─────────────────────────────────────────────────

    def _dedup_by_content(self, results: list[dict]) -> list[dict]:
        seen = set()
        deduped = []
        for r in results:
            doc = r.get("document", "")
            key = doc[:120]
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        return deduped

    # ── 规则评分 ─────────────────────────────────────────────

    def _compute_rule_score(
        self,
        result: dict,
        profile: dict,
        filters: Optional[dict] = None,
    ) -> float:
        """基于元数据匹配度计算规则评分 (0-1)。"""
        metadata = result.get("metadata", {})
        score = 0.0

        # 1. doc_type 权重
        doc_type = metadata.get("doc_type", "其他")
        score += DOC_TYPE_RULE_WEIGHT.get(doc_type, 0.05)

        # 2. curriculum 匹配
        profile_cur = (profile.get("curriculum") or "").strip().upper()
        meta_cur = (metadata.get("curriculum") or "").strip().upper()
        if profile_cur and meta_cur:
            if profile_cur == meta_cur:
                score += 0.30
            elif profile_cur in meta_cur or meta_cur in profile_cur:
                score += 0.15
        elif meta_cur == "通用":
            score += 0.05

        # 3. 学校相关性（非"通用"的学校数据更有参考价值）
        school = metadata.get("school", "")
        if school and school != "通用":
            score += 0.10

        # 4. source_file 中有录取/案例关键词
        source = metadata.get("source_file", "")
        if any(kw in source for kw in ["录取", "案例", "case", "admission"]):
            score += 0.10

        # 5. 年份信息（有明确年份的数据更新）
        year = metadata.get("year", "")
        if year and year != "unknown":
            try:
                y = int(year)
                if y >= 2020:
                    score += 0.10
                elif y >= 2018:
                    score += 0.05
            except ValueError:
                pass

        return min(score, 1.0)

    # ── 多路融合排序 ─────────────────────────────────────────

    def _fusion_rerank(
        self,
        results: list[dict],
        profile: dict,
        filters: Optional[dict] = None,
    ) -> list[dict]:
        """向量相似度 + 规则评分 → 融合排序。"""
        if not results:
            return results

        # 计算规则分
        for r in results:
            r["rule_score"] = round(self._compute_rule_score(r, profile, filters), 4)

        # 归一化向量分（已经是 0-1 similarity，直接使用）
        # 融合
        for r in results:
            r["fusion_score"] = round(
                FUSION_VECTOR_WEIGHT * r.get("similarity", 0)
                + FUSION_RULE_WEIGHT * r["rule_score"],
                4,
            )

        # 按融合分降序
        results.sort(key=lambda r: r["fusion_score"], reverse=True)
        return results

    # ── 结构化元数据过滤 ─────────────────────────────────────

    def _apply_metadata_filter(
        self,
        results: list[dict],
        profile: dict,
        filters: Optional[dict] = None,
    ) -> list[dict]:
        """对检索结果应用元数据精确过滤 + 增强。

        filters 支持:
          - curriculum: 精确匹配课程体系
          - doc_types: 限定文档类型列表
          - school: 限定学校
        """
        if not filters:
            return results

        filtered = []

        req_curriculum = (filters.get("curriculum") or "").strip().upper()
        req_doc_types = filters.get("doc_types") or []
        req_school = (filters.get("school") or "").strip()

        for r in results:
            metadata = r.get("metadata", {})

            # curriculum 精确过滤
            if req_curriculum:
                meta_cur = (metadata.get("curriculum") or "").strip().upper()
                if meta_cur and meta_cur != req_curriculum and meta_cur != "通用":
                    continue

            # doc_type 过滤
            if req_doc_types:
                meta_dt = metadata.get("doc_type", "")
                if meta_dt not in req_doc_types:
                    continue

            # school 过滤
            if req_school:
                meta_school = metadata.get("school", "")
                if req_school not in meta_school:
                    continue

            filtered.append(r)

        return filtered

    # ── 主检索方法 ───────────────────────────────────────────

    def search_similar_cases(
        self,
        profile: dict,
        top_k: int = None,
        filters: Optional[dict] = None,
        apply_fusion: bool = True,
    ) -> dict:
        """画像 → 向量检索 → 元数据过滤 → 多路融合排序。

        Args:
            profile: 学生画像 dict
            top_k: 最终返回数量，默认 RETRIEVAL_TOP_K
            filters: 可选元数据过滤 {"curriculum": "IB", "doc_types": ["录取结果", "顾问笔记"]}
            apply_fusion: 是否启用多路融合，默认 True
        """
        if top_k is None:
            top_k = RETRIEVAL_TOP_K

        # 召回阶段：有过滤条件时扩大召回面，保证目标类型能被命中
        if filters:
            fetch_k = max(top_k * 6, 100)
        else:
            fetch_k = max(top_k * 2, RETRIEVAL_TOP_K_LARGE)

        query_text = self._build_case_query(profile)
        query_embedding = self.embedding_model.encode(
            [query_text], normalize_embeddings=True
        ).tolist()

        raw = self.collection.query(
            query_embeddings=query_embedding,
            n_results=fetch_k,
            include=["documents", "metadatas", "distances"],
        )

        results = []
        if raw["ids"] and raw["ids"][0]:
            for i in range(len(raw["ids"][0])):
                distance = raw["distances"][0][i]
                if distance > 1 - SIMILARITY_THRESHOLD:
                    continue
                results.append({
                    "id": raw["ids"][0][i],
                    "document": raw["documents"][0][i],
                    "metadata": raw["metadatas"][0][i],
                    "distance": distance,
                    "similarity": 1 - distance,
                })

        # 元数据精确过滤
        if filters:
            results = self._apply_metadata_filter(results, profile, filters)

        # 去重
        results = self._dedup_by_content(results)

        # 多路融合排序
        if apply_fusion:
            results = self._fusion_rerank(results, profile, filters)

        # 截断
        results = results[:top_k]

        # 统计
        by_type: dict[str, int] = {}
        for r in results:
            doc_type = r["metadata"].get("doc_type", "其他")
            by_type[doc_type] = by_type.get(doc_type, 0) + 1

        return {
            "query": query_text,
            "total_hits": len(results),
            "results": results,
            "by_doc_type": by_type,
            "filters_applied": filters,
        }

    def search_schools(self, query: str, top_k: int = 10) -> dict:
        query_embedding = self.embedding_model.encode(
            [query], normalize_embeddings=True
        ).tolist()

        raw = self.collection.query(
            query_embeddings=query_embedding,
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        results = []
        if raw["ids"] and raw["ids"][0]:
            for i in range(len(raw["ids"][0])):
                distance = raw["distances"][0][i]
                if distance > 1 - SIMILARITY_THRESHOLD:
                    continue
                results.append({
                    "id": raw["ids"][0][i],
                    "document": raw["documents"][0][i],
                    "metadata": raw["metadatas"][0][i],
                    "distance": distance,
                    "similarity": 1 - distance,
                })

        results = self._dedup_by_content(results)

        return {
            "query": query,
            "total_hits": len(results),
            "results": results,
        }

    # ── 结构化元数据查询（精确匹配） ──────────────────────────

    def search_by_metadata(
        self,
        curriculum: Optional[str] = None,
        doc_type: Optional[str] = None,
        school: Optional[str] = None,
        limit: int = 20,
    ) -> dict:
        """通过 ChromaDB where 条件精确查询元数据。

        用于补充检索：例如"找所有 IB + 录取结果"的数据。
        """
        where_parts = []
        if curriculum:
            where_parts.append({"curriculum": {"$eq": curriculum}})
        if doc_type:
            where_parts.append({"doc_type": {"$eq": doc_type}})
        if school:
            where_parts.append({"school": {"$eq": school}})

        if len(where_parts) == 0:
            where = None
        elif len(where_parts) == 1:
            where = where_parts[0]
        else:
            where = {"$and": where_parts}

        raw = self.collection.get(
            where=where,
            limit=limit,
            include=["documents", "metadatas"],
        )

        results = []
        for i in range(len(raw["ids"])):
            results.append({
                "id": raw["ids"][i],
                "document": raw["documents"][i],
                "metadata": raw["metadatas"][i],
            })

        return {
            "total_hits": len(results),
            "results": results,
            "filters": {
                "curriculum": curriculum,
                "doc_type": doc_type,
                "school": school,
            },
        }
