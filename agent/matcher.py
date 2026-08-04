import re
import logging
from collections import defaultdict
from statistics import median
from typing import Optional

logger = logging.getLogger(__name__)


# ── 分数解析 ──────────────────────────────────────────────────

class ScoreParser:
    """解析和归一化学生标化成绩。"""

    @staticmethod
    def parse_gpa(raw, curriculum: Optional[str] = None) -> Optional[float]:
        """解析 GPA，支持多种课程体系。

        - 4.0 scale: 3.9 → 3.9
        - 100 scale: 90 → 3.6
        - IB: 42 (24-45 range) → normalize to 4.0 scale
        - "3.9/4.0" or "42/45" format
        - "预估 42 分" → extract number
        """
        if raw is None:
            return None
        raw = str(raw).strip()
        cur = (curriculum or "").strip().upper()

        # "3.9/4.0" or "3.9 / 4.0" or "42/45"
        m = re.search(r'([\d.]+)\s*/\s*([\d.]+)', raw)
        if m:
            score, scale = float(m.group(1)), float(m.group(2))
            if scale > 0:
                if scale == 45 and score >= 24:
                    return round(score / 45 * 4.0, 2)
                return round(score / min(scale, 100) * 4.0, 2)

        # Extract any number from string (handles "预估 42 分", "约 3.9", etc.)
        num_match = re.search(r'([\d.]+)', raw)
        if num_match:
            val = float(num_match.group(1))
        else:
            return None

        # IB total score (24-45 range)
        if cur == "IB" and 24 <= val <= 45:
            return round(val / 45 * 4.0, 2)
        if 24 <= val <= 45 and ("IB" in raw.upper() or "IB" in cur):
            return round(val / 45 * 4.0, 2)

        # Regular: if > 10, likely 100-scale percentage
        if val > 10:
            val = val / 25

        # Weighted GPA can be > 4.0
        return round(min(val, 5.0), 2)

    @staticmethod
    def parse_toefl(raw) -> Optional[int]:
        if raw is None:
            return None
        raw = str(raw).strip()
        try:
            val = int(float(raw))
            return val if 0 < val <= 120 else None
        except ValueError:
            pass
        m = re.search(r'(\d{2,3})', raw)
        if m:
            val = int(m.group(1))
            return val if 0 < val <= 120 else None
        return None

    @staticmethod
    def parse_ielts(raw) -> Optional[float]:
        if raw is None:
            return None
        raw = str(raw).strip()
        try:
            val = float(raw)
            return val if 1.0 <= val <= 9.0 else None
        except ValueError:
            pass
        m = re.search(r'(\d\.?\d?)', raw)
        if m:
            val = float(m.group(1))
            return val if 1.0 <= val <= 9.0 else None
        return None

    @staticmethod
    def parse_sat(raw) -> Optional[int]:
        if raw is None:
            return None
        raw = str(raw).strip()
        try:
            val = int(float(raw))
            return val if 400 <= val <= 1600 else None
        except ValueError:
            pass
        m = re.search(r'(\d{3,4})', raw)
        if m:
            val = int(m.group(1))
            return val if 400 <= val <= 1600 else None
        return None

    @staticmethod
    def parse_act(raw) -> Optional[int]:
        if raw is None:
            return None
        raw = str(raw).strip()
        try:
            val = int(float(raw))
            return val if 1 <= val <= 36 else None
        except ValueError:
            pass
        m = re.search(r'(\d{1,2})', raw)
        if m:
            val = int(m.group(1))
            return val if 1 <= val <= 36 else None
        return None


# ── 正则：从文档中抽取分数 ────────────────────────────────────

# 匹配模式 (pattern, parser_method, value_group_index)
SCORE_PATTERNS = [
    # TOEFL: "TOEFL108", "托福 108", "TOEFL: 108", "TOEFL 108+"
    (r'(?:TOEFL|托福|toefl)\s*[:：]?\s*(\d{2,3})', 'parse_toefl'),
    (r'托福\s*(\d{2,3})', 'parse_toefl'),
    # IELTS: "IELTS7.5", "雅思 7.5", "IELTS: 7.5"
    (r'(?:IELTS|雅思|ielts)\s*[:：]?\s*([\d.]+)', 'parse_ielts'),
    # SAT: "SAT1480", "SAT 1480", "SAT: 1480"
    (r'(?:SAT|sat)\s*[:：]?\s*(\d{3,4})', 'parse_sat'),
    # ACT: "ACT32", "ACT 32", "ACT: 32"
    (r'(?:ACT|act)\s*[:：]?\s*(\d{1,2})', 'parse_act'),
    # GPA: "GPA3.9", "GPA 3.9/4.0", "GPA: 3.9"
    (r'(?:GPA|gpa)\s*[:：]?\s*([\d.]+(?:\s*/\s*[\d.]+)?)', 'parse_gpa'),
    # GPA percentage: "均分90" "平均分 88"
    (r'(?:均分|平均分|成绩均分)\s*[:：]?\s*(\d{2,3})', 'parse_gpa'),
]

parser = ScoreParser()


def _extract_scores_from_text(text: str) -> dict[str, list]:
    """从文本中抽取所有标化分数。"""
    found: dict[str, list] = defaultdict(list)
    text = str(text)

    for pattern, method_name in SCORE_PATTERNS:
        method = getattr(parser, method_name)
        for m in re.finditer(pattern, text, re.IGNORECASE):
            val = method(m.group(1))
            if val is not None:
                key = method_name.replace('parse_', '')  # gpa, toefl, ielts, sat, act
                if val not in found[key]:
                    found[key].append(val)

    return dict(found)


def _summarize_scores(scores: list) -> Optional[dict]:
    """汇总一组成绩的统计信息。"""
    if not scores:
        return None
    s = sorted(scores)
    n = len(s)
    return {
        "count": n,
        "min": s[0],
        "max": s[-1],
        "median": round(median(s), 2),
        "p25": s[max(0, n // 4)],
        "p75": s[min(n - 1, n * 3 // 4)],
        "samples": s[:10],
    }


# ── 主分类器 ──────────────────────────────────────────────────

# 各指标在综合评分中的权重
METRIC_WEIGHTS = {
    "gpa": 0.30,
    "sat": 0.30,
    "act": 0.20,
    "toefl": 0.25,
    "ielts": 0.25,
}

# 三级阈值
TIER_THRESHOLD_SAFETY = 0.67   # >= safety
TIER_THRESHOLD_MATCH = 0.33    # >= match, < safety
# < 0.33 → reach


class Matcher:
    """冲刺 / 匹配 / 保底 三级分级算法。

    基于学生标化成绩与知识库中学校录取数据区间的量化对比，
    将学校划分为 冲刺(reach)、匹配(match)、保底(safety) 三级。
    """

    def __init__(self):
        self.parser = ScoreParser()

    def classify(
        self,
        profile: dict,
        search_results: dict,
    ) -> dict:
        """对学生画像和检索结果进行三级分类。

        Args:
            profile: 学生画像 (curriculum, gpa, toefl, ielts, sat, act 等)
            search_results: retriever.search_similar_cases 的返回结果

        Returns:
            {
                "student_scores": {...},
                "schools": [{name, tier, match_score, metrics, doc_count}],
                "summary": {reach, match, safety, total}
            }
        """
        # 1. 解析学生成绩
        student = self._parse_student(profile)

        # 2. 从检索结果中提取各学校录取数据
        school_data = self._aggregate_school_data(search_results.get("results", []))

        # 3. 对每所学校分级
        classified = []
        for school_name, data in school_data.items():
            tier, score, metrics = self._classify_school(student, data)
            classified.append({
                "name": school_name,
                "tier": tier,
                "match_score": score,
                "metrics": metrics,
                "doc_count": data["doc_count"],
            })

        # 4. 排序: safety → match → reach，同 tier 内 match_score 降序
        tier_order = {"safety": 0, "match": 1, "reach": 2}
        classified.sort(key=lambda s: (tier_order.get(s["tier"], 9), -s["match_score"]))

        reach = sum(1 for s in classified if s["tier"] == "reach")
        match = sum(1 for s in classified if s["tier"] == "match")
        safety = sum(1 for s in classified if s["tier"] == "safety")

        logger.info(
            "Matcher classified %d schools — reach:%d match:%d safety:%d",
            len(classified), reach, match, safety,
        )

        return {
            "student_scores": {
                "gpa": student.get("gpa"),
                "toefl": student.get("toefl"),
                "ielts": student.get("ielts"),
                "sat": student.get("sat"),
                "act": student.get("act"),
            },
            "schools": classified,
            "summary": {
                "reach": reach,
                "match": match,
                "safety": safety,
                "total": len(classified),
            },
        }

    # ── 学生成绩解析 ─────────────────────────────────────────

    def _parse_student(self, profile: dict) -> dict:
        curriculum = profile.get("curriculum")
        return {
            "gpa": self.parser.parse_gpa(profile.get("gpa"), curriculum),
            "toefl": self.parser.parse_toefl(profile.get("toefl")),
            "ielts": self.parser.parse_ielts(profile.get("ielts")),
            "sat": self.parser.parse_sat(profile.get("sat")),
            "act": self.parser.parse_act(profile.get("act")),
        }

    # ── 常见大学名称关键词（中英文） ─────────────────────────

    _SCHOOL_KEYWORDS = [
        # 美国 Top 50
        "Harvard", "Stanford", "MIT", "Massachusetts Institute", "Yale", "Princeton",
        "Columbia", "Chicago", "UPenn", "Pennsylvania", "Duke", "Johns Hopkins",
        "Northwestern", "Caltech", "Dartmouth", "Brown", "Cornell", "Vanderbilt",
        "Rice", "WashU", "Washington University", "UCLA", "UC Berkeley", "Berkeley",
        "USC", "Southern California", "Carnegie Mellon", "CMU", "Michigan", "UMich",
        "NYU", "New York University", "Emory", "Georgetown", "Virginia", "UVA",
        "UNC", "Wake Forest", "Tufts", "Boston College", "Boston University",
        "Georgia Tech", "UIUC", "Illinois", "Purdue", "UT Austin", "Texas A&M",
        "Wisconsin", "Madison", "Ohio State", "OSU", "Maryland", "Northeastern",
        "Case Western", "Rochester", "UC San Diego", "UCSD", "UC Davis",
        "UC Irvine", "UC Santa Barbara", "UC Santa Cruz",
        "威廉姆斯", "阿默斯特", "斯沃斯莫尔", "韦尔斯利", "波莫纳",
        # 英国
        "Oxford", "Cambridge", "Imperial College", "Imperial", "LSE",
        "London School of Economics", "UCL", "University College London",
        "Edinburgh", "Manchester", "Warwick", "KCL", "King's College",
        "Durham", "Bristol", "Southampton", "Glasgow", "Birmingham",
        "Leeds", "Sheffield", "Nottingham", "St Andrews",
        # 亚洲
        "香港大学", "HKU", "香港中文大学", "CUHK", "香港科技大学", "HKUST",
        "香港城市大学", "香港理工大学", "港大", "港中文", "港科大",
        "新加坡国立", "NUS", "南洋理工", "NTU",
        "东京大学", "早稻田",
    ]

    _SCHOOL_PATTERN = re.compile(
        r'\b(?:' + '|'.join(re.escape(kw) for kw in _SCHOOL_KEYWORDS) + r')\b',
        re.IGNORECASE,
    )

    def _extract_schools_from_text(self, text: str) -> list[str]:
        """从文本中提取已知大学名称。"""
        matches = self._SCHOOL_PATTERN.findall(text)
        # 去重保持顺序
        seen = set()
        result = []
        for m in matches:
            if m.lower() not in seen:
                seen.add(m.lower())
                result.append(m)
        return result

    # ── 学校数据聚合 ─────────────────────────────────────────

    def _aggregate_school_data(self, results: list[dict]) -> dict:
        """从检索结果中按学校聚合分数数据。

        - 优先使用元数据中的 school 字段
        - 若 school 为"通用"，尝试从文档内容中提取学校名称
        """
        school_docs: dict[str, list[str]] = defaultdict(list)

        for r in results:
            school_meta = r.get("metadata", {}).get("school", "").strip()
            doc = r.get("document", "")

            if school_meta and school_meta != "通用":
                school_docs[school_meta].append(doc)
            else:
                # 尝试从文档内容中提取学校名
                extracted = self._extract_schools_from_text(doc)
                for sch in extracted:
                    school_docs[sch].append(doc)

        # 对每所学校汇总分数
        aggregated = {}
        for school, docs in school_docs.items():
            all_scores = {
                "gpa": [],
                "toefl": [],
                "ielts": [],
                "sat": [],
                "act": [],
            }

            for doc in docs:
                extracted = _extract_scores_from_text(doc)
                for key in all_scores:
                    if key in extracted:
                        all_scores[key].extend(extracted[key])

            # 去重并排序
            for key in all_scores:
                all_scores[key] = sorted(set(all_scores[key]))

            summary = {}
            for key in all_scores:
                summary[key] = _summarize_scores(all_scores[key])

            aggregated[school] = {
                "doc_count": len(docs),
                **summary,
            }

        return aggregated

    # ── 单所学校分级 ─────────────────────────────────────────

    def _classify_school(
        self,
        student: dict,
        school_data: dict,
    ) -> tuple[str, float, dict]:
        """对单所学校分级。

        Returns:
            (tier, match_score, metrics_detail)
        """
        scores = []
        weights = []
        detail = {}

        # GPA: weight 0.30
        if student.get("gpa") is not None and school_data.get("gpa"):
            s, d = self._metric_score(student["gpa"], school_data["gpa"])
            scores.append(s)
            weights.append(METRIC_WEIGHTS["gpa"])
            detail["gpa"] = d

        # SAT: weight 0.30 (if present; if ACT present instead, use that)
        if student.get("sat") is not None and school_data.get("sat"):
            s, d = self._metric_score(student["sat"], school_data["sat"])
            scores.append(s)
            weights.append(METRIC_WEIGHTS["sat"])
            detail["sat"] = d

        # ACT: weight 0.20 (or 0.30 if no SAT)
        if student.get("act") is not None and school_data.get("act"):
            w = 0.30 if not (student.get("sat") and school_data.get("sat")) else 0.20
            s, d = self._metric_score(student["act"], school_data["act"])
            scores.append(s)
            weights.append(w)
            detail["act"] = d

        # TOEFL: weight 0.25
        if student.get("toefl") is not None and school_data.get("toefl"):
            s, d = self._metric_score(student["toefl"], school_data["toefl"])
            scores.append(s)
            weights.append(METRIC_WEIGHTS["toefl"])
            detail["toefl"] = d

        # IELTS: weight 0.25 (only if no TOEFL)
        if student.get("ielts") is not None and school_data.get("ielts"):
            if not (student.get("toefl") and school_data.get("toefl")):
                s, d = self._metric_score(student["ielts"], school_data["ielts"])
                scores.append(s)
                weights.append(METRIC_WEIGHTS["ielts"])
                detail["ielts"] = d

        # 无数据 → 默认 match
        if not scores:
            return "match", 0.50, {"note": "insufficient_data"}

        # 加权综合分
        total_w = sum(weights)
        match_score = round(sum(s * w for s, w in zip(scores, weights)) / total_w, 4)

        if match_score >= TIER_THRESHOLD_SAFETY:
            tier = "safety"
        elif match_score >= TIER_THRESHOLD_MATCH:
            tier = "match"
        else:
            tier = "reach"

        return tier, match_score, detail

    # ── 单指标对比分 ─────────────────────────────────────────

    def _metric_score(
        self,
        student_val: float,
        school_stats: dict,
    ) -> tuple[float, dict]:
        """计算单一指标的学生 vs 学校对比分 (0-1)。

        Returns:
            (score, detail_dict)
        """
        median_val = school_stats["median"]
        p25 = school_stats["p25"]
        p75 = school_stats["p75"]
        count = school_stats["count"]

        if median_val == 0:
            return 0.5, {"student": student_val, "school_median": median_val,
                         "result": "no_data"}

        detail = {
            "student": student_val,
            "school_median": median_val,
            "school_p25": p25,
            "school_p75": p75,
            "sample_count": count,
        }

        # 学生明显高于学校中位数 → safety
        if student_val >= p75:
            excess = (student_val - p75) / max(p75 * 0.1, 1)
            score = min(1.0, 0.70 + excess * 0.15)
            detail["result"] = "above_range"
        # 学生明显低于学校中位数 → reach
        elif student_val <= p25:
            deficit = (p25 - student_val) / max(p25 * 0.1, 1)
            score = max(0.05, 0.30 - deficit * 0.15)
            detail["result"] = "below_range"
        # 学生在中间区间 → match
        else:
            if p75 > p25:
                position = (student_val - p25) / (p75 - p25)
            else:
                position = 0.5
            score = 0.30 + position * 0.40
            detail["result"] = "in_range"

        return round(score, 4), detail

    # ── 格式化输出 ───────────────────────────────────────────

    def format_summary_text(self, result: dict) -> str:
        """将分类结果格式化为可嵌入 prompt 的纯文本。"""
        lines = ["## 选校分级结果 (冲刺/匹配/保底)"]
        lines.append("")

        student = result.get("student_scores", {})
        parts = []
        if student.get("gpa"):
            parts.append(f"GPA {student['gpa']}")
        if student.get("toefl"):
            parts.append(f"TOEFL {student['toefl']}")
        if student.get("ielts"):
            parts.append(f"IELTS {student['ielts']}")
        if student.get("sat"):
            parts.append(f"SAT {student['sat']}")
        if student.get("act"):
            parts.append(f"ACT {student['act']}")
        if parts:
            lines.append(f"学生成绩: {', '.join(parts)}")
            lines.append("")

        summary = result.get("summary", {})
        lines.append(
            f"分类统计: 冲刺 {summary.get('reach', 0)} 所 | "
            f"匹配 {summary.get('match', 0)} 所 | "
            f"保底 {summary.get('safety', 0)} 所"
        )
        lines.append("")

        tier_labels = {"reach": "冲刺", "match": "匹配", "safety": "保底"}
        for school in result.get("schools", []):
            label = tier_labels.get(school["tier"], school["tier"])
            score = school.get("match_score", 0)
            metrics = school.get("metrics", {})

            metric_parts = []
            for key in ["gpa", "toefl", "ielts", "sat", "act"]:
                if key in metrics and isinstance(metrics[key], dict):
                    m = metrics[key]
                    metric_parts.append(
                        f"{key.upper()}: 学生{m['student']} vs "
                        f"学校中位{m['school_median']} ({m.get('result', '?')})"
                    )

            lines.append(
                f"- [{label}] {school['name']} "
                f"(综合匹配分: {score:.0%}, 数据来源: {school.get('doc_count', 0)} 条)"
            )
            for mp in metric_parts:
                lines.append(f"    {mp}")

        return "\n".join(lines)
