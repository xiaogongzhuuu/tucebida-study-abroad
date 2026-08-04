import json

from openai import OpenAI

from .config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_CHAT_MODEL

PROFILE_SYSTEM_PROMPT = """你是一位经验丰富的留学顾问，擅长从学生描述中提取关键信息。

请从用户的自然语言描述中提取以下结构化信息，输出严格合法的 JSON。
只输出 JSON，不要包含 markdown 代码块标记。

提取规则：
- 未提及的字段设为 null
- GPA 保留原始数值或描述
- 标化考试成绩提取分数和科目
- 专业意向是一个列表，按提及顺序排列
- 国家偏好是一个列表

输出 schema:
{
  "curriculum": "string | null  (课程体系, 如 IB/AP/A-Level/普高/美高)",
  "gpa": "string | null",
  "toefl": "string | null",
  "ielts": "string | null",
  "sat": "string | null",
  "act": "string | null",
  "ap_scores": "string | null",
  "major_interest": ["string"],
  "activities": ["string"],
  "country_pref": ["string"],
  "budget": "string | null",
  "grade_level": "string | null  (当前年级, 如 高二/11年级/G11)",
  "family_income": "string | null  (家庭年收入，如 50万/100万/200万+)",
  "parents_occupation": "string | null  (父母职业与职位，可补充职级或行业)",
  "family_assets": "string | null  (家庭资产简述，如房产/企业/投资等)",
  "living_city": "string | null  (居住城市)",
  "notes": "string | null  (其他补充信息)"
}
"""


class ProfileExtractor:
    def __init__(self):
        self.client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
        )

    def extract(self, user_text: str) -> dict:
        response = self.client.chat.completions.create(
            model=DEEPSEEK_CHAT_MODEL,
            messages=[
                {"role": "system", "content": PROFILE_SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content.strip()
        profile = json.loads(raw)

       
        profile.setdefault("curriculum", None)
        profile.setdefault("gpa", None)
        profile.setdefault("toefl", None)
        profile.setdefault("ielts", None)
        profile.setdefault("sat", None)
        profile.setdefault("act", None)
        profile.setdefault("ap_scores", None)
        profile.setdefault("major_interest", [])
        profile.setdefault("activities", [])
        profile.setdefault("country_pref", [])
        profile.setdefault("budget", None)
        profile.setdefault("grade_level", None)
        profile.setdefault("family_income", None)
        profile.setdefault("parents_occupation", None)
        profile.setdefault("family_assets", None)
        profile.setdefault("living_city", None)
        profile.setdefault("notes", None)

        return profile
