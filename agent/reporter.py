import json
import logging
from typing import Iterator, Optional

from openai import OpenAI

from .config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_CHAT_MODEL

logger = logging.getLogger(__name__)

REPORT_SYSTEM_PROMPT = """你是一位资深留学顾问 AI，拥有 10 年以上中国学生海外名校申请指导经验。

## 你的任务
根据学生画像和知识库检索到的相关数据，生成一份个性化的选校推荐报告。

## 知识库数据说明
下方提供的数据来自真实历史案例和学校资料库。每条数据标注了：
- **类型**：录取结果 / 顾问笔记 / school_profile 等
- **匹配度**：向量相似度 + 规则评分的融合分数（0-1，越高越相关）

请优先参考高匹配度的数据，对低匹配度数据可酌情忽略。

## 输出格式（严格按此结构，使用 Markdown）

### 📋 学生画像概述
用 2-3 句话总结学生背景，包括：学术实力评估（基于 GPA/标化）、课程体系特点、专业方向、核心优势与需注意的短板。

### 🏫 推荐学校分析
选取 5-8 所学校进行分析，按推荐度排列。每所学校包含：

**序号. 学校英文名（中文名）**
- **匹配亮点**：结合学生具体条件（如 GPA、TOEFL、SAT）说明匹配度
- **数据参考**：引用知识库中相关案例或录取数据（标注案例编号和年份）
- **申请建议**：针对该校特点给出 1 条具体建议

### 📊 选校策略
- 整体定位（冲刺/匹配/保底的大致分布）
- 标化/活动方面可重点强化的方向
- 时间线建议（基于当前年级）

### ⚠️ 注意事项
- 列出 2-3 条申请中需要特别关注的风险点或建议

## 知识库检索结果
{context}

## 写作要求
- 必须引用知识库中的具体数据（案例编号、分数、年份），否则报告缺乏说服力
- 如果没有足够匹配的案例，诚实说明并基于普遍规律给出建议
- 学校推荐要具体，不要只说"建议申请排名前30的学校"
- 用中文撰写，学校名、专业名保持英文
- 不要使用"该校"等模糊指代，明确写出学校名称"""

REPORT_SYSTEM_PROMPT_FALLBACK = """你是一位资深留学顾问 AI，拥有 10 年以上中国学生海外名校申请指导经验。

## 你的任务
根据学生画像生成个性化的选校推荐报告。

⚠️ 注意：知识库中未找到与该学生高度匹配的历史案例，请基于你的申请经验和普遍规律给出建议，并在报告中诚实说明这一点。

## 输出格式（严格按此结构，使用 Markdown）

### 📋 学生画像概述
用 2-3 句话总结学生背景。

### 🏫 推荐学校分析
选取 5-8 所学校进行分析，按推荐度排列。每所学校包含：
**序号. 学校英文名（中文名）**
- **匹配亮点**：结合学生条件说明匹配度
- **申请建议**：针对该校特点给出具体建议

### 📊 选校策略
整体定位、强化方向、时间线建议。

### ⚠️ 注意事项
2-3 条风险点或建议。

## 写作要求
- 基于你的知识推荐真实存在的学校
- 学校推荐要具体，给出明确的录取区间参考
- 用中文撰写，学校名、专业名保持英文
- 在报告中说明：因缺乏足够匹配的历史案例，以下建议基于普遍申请规律"""


class ReportGenerator:
    def __init__(self):
        self.client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
        )

    def _format_context(self, search_result: dict, max_chunks: int = 10) -> tuple[str, bool]:
        """将检索结果格式化为 prompt 上下文。

        Returns:
            (formatted_context, has_sufficient_data): 上下文文本和是否有足够数据
        """
        results = search_result.get("results", [])
        if not results:
            return "（无相关历史案例数据）", False

        # 筛选有足够融合分的结果
        quality_results = [r for r in results if r.get("fusion_score", 0) >= 0.15]
        if not quality_results:
            quality_results = results[:max_chunks]

        has_sufficient = len(quality_results) >= 3

        chunks = []
        for i, r in enumerate(quality_results[:max_chunks], 1):
            meta = r.get("metadata", {})
            fusion = r.get("fusion_score", 0)

            header = (
                f"[案例 {i}] "
                f"类型: {meta.get('doc_type', '未知')} | "
                f"学校: {meta.get('school', '未知')} | "
                f"课程: {meta.get('curriculum', '未知')} | "
                f"年份: {meta.get('year', '未知')} | "
                f"匹配度: {fusion:.0%}"
            )
            doc = r.get("document", "")
            # 截断过长文档
            if len(doc) > 1500:
                doc = doc[:1500] + "..."
            chunks.append(f"{header}\n{doc}")

        return "\n\n---\n\n".join(chunks), has_sufficient

    def generate(
        self,
        profile: dict,
        search_result: dict,
        stream: bool = False,
        classify_result: Optional[dict] = None,
    ):
        """生成选校报告。

        Args:
            profile: 学生画像
            search_result: retriever.search_similar_cases 返回结果
            stream: 是否流式输出 (SSE)
            classify_result: matcher.classify 三级分级结果 (可选)

        Returns:
            stream=False: 完整报告文本 (str)
            stream=True: OpenAI stream iterator
        """
        context, has_sufficient = self._format_context(search_result)
        classification = self._format_classification(classify_result)

        if has_sufficient:
            system_prompt = REPORT_SYSTEM_PROMPT.format(context=context)
        else:
            system_prompt = REPORT_SYSTEM_PROMPT_FALLBACK

        user_msg = self._build_user_message(profile, classification)

        total_hits = search_result.get("total_hits", 0)
        logger.info(
            "Generating report — hits: %d, sufficient: %s, stream: %s",
            total_hits, has_sufficient, stream,
        )

        if stream:
            return self.client.chat.completions.create(
                model=DEEPSEEK_CHAT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.7,
                stream=True,
            )

        response = self.client.chat.completions.create(
            model=DEEPSEEK_CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.7,
        )

        content = response.choices[0].message.content
        return content

    def generate_stream_sse(
        self,
        profile: dict,
        search_result: dict,
        classify_result: Optional[dict] = None,
    ) -> Iterator[str]:
        """流式生成选校报告，输出 SSE 格式字符串。

        每条 yield 一个完整的 SSE data 行。
        """
        stream = self.generate(profile, search_result, stream=True,
                               classify_result=classify_result)
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield f"data: {json.dumps({'content': delta.content})}\n\n"
        yield "data: [DONE]\n\n"

    def _format_classification(self, classify_result: Optional[dict]) -> Optional[str]:
        """格式化分级结果用于 prompt。"""
        if not classify_result:
            return None

        schools = classify_result.get("schools", [])
        if not schools:
            return None

        tier_labels = {"reach": "冲刺", "match": "匹配", "safety": "保底"}
        lines = ["## 算法预分级结果（基于标化成绩 vs 学校录取区间）"]
        lines.append("")

        summary = classify_result.get("summary", {})
        lines.append(
            f"共 {summary.get('total', len(schools))} 所学校: "
            f"冲刺 {summary.get('reach', 0)} | "
            f"匹配 {summary.get('match', 0)} | "
            f"保底 {summary.get('safety', 0)}"
        )
        lines.append("")

        for school in schools:
            label = tier_labels.get(school["tier"], school["tier"])
            score = school.get("match_score", 0)
            metrics = school.get("metrics", {})
            detail_parts = []
            for key in ["gpa", "toefl", "ielts", "sat", "act"]:
                if key in metrics and isinstance(metrics[key], dict):
                    m = metrics[key]
                    detail_parts.append(
                        f"{key.upper()}: 学生{m['student']} vs "
                        f"中位{m['school_median']}({m.get('result', '?')})"
                    )
            lines.append(
                f"- [{label}] {school['name']} "
                f"(匹配分 {score:.0%}, 数据 {school.get('doc_count', 0)}条)"
            )
            if detail_parts:
                lines.append(f"  {' | '.join(detail_parts)}")

        return "\n".join(lines)

    def _build_user_message(self, profile: dict, classification: Optional[str] = None) -> str:
        parts = ["请为以下学生生成选校推荐报告：\n"]

        if profile.get("curriculum"):
            parts.append(f"- 课程体系: {profile['curriculum']}")
        if profile.get("gpa"):
            parts.append(f"- GPA / 预估分: {profile['gpa']}")
        if profile.get("toefl"):
            parts.append(f"- TOEFL: {profile['toefl']}")
        if profile.get("ielts"):
            parts.append(f"- IELTS: {profile['ielts']}")
        if profile.get("sat"):
            parts.append(f"- SAT: {profile['sat']}")
        if profile.get("act"):
            parts.append(f"- ACT: {profile['act']}")
        if profile.get("ap_scores"):
            parts.append(f"- AP: {profile['ap_scores']}")

        major = profile.get("major_interest")
        if major:
            parts.append(f"- 专业意向: {', '.join(major)}")

        country = profile.get("country_pref")
        if country:
            parts.append(f"- 意向国家: {', '.join(country)}")

        activities = profile.get("activities")
        if activities:
            parts.append(f"- 活动/竞赛: {', '.join(activities)}")

        if profile.get("budget"):
            parts.append(f"- 预算: {profile['budget']}")
        if profile.get("grade_level"):
            parts.append(f"- 当前年级: {profile['grade_level']}")
        if profile.get("notes"):
            parts.append(f"- 补充说明: {profile['notes']}")

        # 附加分级数据
        if classification:
            parts.append("")
            parts.append(classification)
            parts.append("")
            parts.append("请在报告中参考上述分级，重点关注匹配和冲刺的学校，"
                         "并对分级结果中的数据依据加以说明。")

        return "\n".join(parts)
