"""
研究生项目统一 Schema 定义 + 数据提取与校验工具。

覆盖字段 (13项):
  Application Materials, Interview Requirements, Application Deadlines,
  Academic Requirements, GRE GMAT Requirements, English Proficiency Requirements,
  Program Overview, Curriculum, Cost of Attendance, Financial Aid,
  Multiple Applications, Deferral Admission Policy, Conditional Admission Policy
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


# ── 枚举定义 ──────────────────────────────────────────────

class Country(str, Enum):
    UK = "UK"
    HK = "HK"
    SG = "SG"

class DegreeType(str, Enum):
    MSc = "MSc"
    MA = "MA"
    MSA = "MSA"
    MBA = "MBA"
    MBAI = "MBAI"
    LLM = "LLM"
    JD = "JD"
    MiM = "MiM"
    MPA = "MPA"
    MSE = "MSE"
    MQF = "MQF"
    MSFE = "MSFE"
    MEI = "MEI"
    MITB = "MITB"
    MAA = "MAA"
    MDS = "MDS"
    MSocSc = "MSocSc"
    MTech = "MTech"
    MST = "MST"
    MDSE = "MDSE"
    MSc_NUS = "M.Sc."  # NUS 使用 M.Sc. 格式

class MajorDirection(str, Enum):
    ANALYTICS = "Analytics"
    FINANCE = "Finance"
    ACCOUNTING = "Accounting"
    MANAGEMENT = "Management"
    COMPUTER_SCIENCE = "Computer Science"
    LAW = "Law"
    ECONOMICS = "Economics"
    MARKETING = "Marketing"
    DATA_SCIENCE = "Data Science"
    ACTUARIAL = "Actuarial"
    HEALTH = "Health"
    ENVIRONMENTAL = "Environmental"
    URBAN = "Urban"
    HR = "Human Resources"
    SUPPLY_CHAIN = "Supply Chain"
    RISK = "Risk"
    DIGITAL = "Digital"
    SUSTAINABILITY = "Sustainability"
    SOCIAL = "Social"
    PSYCHOLOGY = "Psychology"
    GEOGRAPHY = "Geography"
    LOGISTICS = "Logistics"
    CYBER = "Cyber Security"
    INSURANCE = "Insurance"
    ENTERPRISE = "Enterprise"
    GENERAL = "General"


# ── 标准字段名 ────────────────────────────────────────────

STD_FIELDS = [
    "Application Materials",
    "Interview Requirements",
    "Application Deadlines",
    "Academic Requirements",
    "GRE GMAT Requirements",
    "English Proficiency Requirements",
    "Program Overview",
    "Curriculum",
    "Cost of Attendance",
    "Financial Aid",
    "Multiple Applications",
    "Deferral Admission Policy",
    "Conditional Admission Policy",
]


# ── 学校 → 国家映射 ───────────────────────────────────────

SCHOOL_COUNTRY = {
    # UK
    "UCL": Country.UK, "Imperial": Country.UK, "LSE": Country.UK,
    "KCL": Country.UK, "Warwick": Country.UK, "Edinburgh": Country.UK,
    "Manchester": Country.UK, "Leeds": Country.UK, "Liverpool": Country.UK,
    "Exeter": Country.UK, "Cardiff": Country.UK, "QUB": Country.UK,
    "QMUL": Country.UK, "Southampton": Country.UK, "Glasgow": Country.UK,
    "Bristol": Country.UK, "Newcastle": Country.UK, "Nottingham": Country.UK,
    "Durham": Country.UK, "Lancaster": Country.UK, "Sheffield": Country.UK,
    "Birmingham": Country.UK, "Bath": Country.UK, "York": Country.UK,
    # HK
    "HKU": Country.HK, "CUHK": Country.HK, "PolyU": Country.HK,
    "CityU": Country.HK, "HKUST": Country.HK, "HKLU": Country.HK,
    # SG
    "NUS": Country.SG, "NTU": Country.SG, "SMU": Country.SG,
}


# ── 专业方向关键词匹配 ────────────────────────────────────

DIRECTION_KEYWORDS = [
    (MajorDirection.ANALYTICS, ["analytics", "business analytics", "data analytics"]),
    (MajorDirection.FINANCE, ["finance", "financial", "banking", "investment", "wealth"]),
    (MajorDirection.ACCOUNTING, ["accounting"]),
    (MajorDirection.MANAGEMENT, ["management", "human capital"]),
    (MajorDirection.COMPUTER_SCIENCE, ["computer science", "machine learning", "artificial intelligence"]),
    (MajorDirection.LAW, ["law", "juris doctor", "legal"]),
    (MajorDirection.ECONOMICS, ["economics", "economy"]),
    (MajorDirection.MARKETING, ["marketing"]),
    (MajorDirection.DATA_SCIENCE, ["data science"]),
    (MajorDirection.ACTUARIAL, ["actuarial"]),
    (MajorDirection.HEALTH, ["health", "healthcare"]),
    (MajorDirection.ENVIRONMENTAL, ["environmental", "earth", "energy systems"]),
    (MajorDirection.URBAN, ["urban", "spatio-temporal"]),
    (MajorDirection.HR, ["human resource", "people analytics", "organisational"]),
    (MajorDirection.SUPPLY_CHAIN, ["supply chain"]),
    (MajorDirection.RISK, ["risk"]),
    (MajorDirection.DIGITAL, ["digital marketing"]),
    (MajorDirection.SUSTAINABILITY, ["sustainability"]),
    (MajorDirection.SOCIAL, ["social data", "social analytics"]),
    (MajorDirection.PSYCHOLOGY, ["psychology", "behavioural"]),
    (MajorDirection.GEOGRAPHY, ["geographic", "geospatial"]),
    (MajorDirection.LOGISTICS, ["logistics"]),
    (MajorDirection.CYBER, ["cyber"]),
    (MajorDirection.INSURANCE, ["insurance", "actuarial science and insurance"]),
    (MajorDirection.ENTERPRISE, ["enterprise business", "industrial data"]),
]
DIRECTION_KEYWORDS.sort(key=lambda x: len(x[1][0]), reverse=True)  # 长关键词优先匹配


# ── 学位规范化 ────────────────────────────────────────────

NUS_MSC_PATTERN = re.compile(r"^M\.Sc\.$")

def normalize_degree(raw: str) -> DegreeType:
    """将文件名中的学位标识规范化为 DegreeType 枚举。"""
    d = raw.strip()
    if d in MASTER_ALIASES:
        return DegreeType.MSc
    if NUS_MSC_PATTERN.match(d):
        return DegreeType.MSc_NUS
    for dt in DegreeType:
        if d == dt.value:
            return dt
    # fallback: 大小写模糊匹配
    upper = d.upper()
    for dt in DegreeType:
        if upper == dt.value.upper():
            return dt
    raise ValueError(f"Unknown degree type: {raw}")


# ── 数据模型 ──────────────────────────────────────────────

@dataclass
class FieldEntry:
    url: str
    content: str

    @staticmethod
    def from_dict(d: dict) -> FieldEntry:
        return FieldEntry(url=d.get("url", ""), content=d.get("content", ""))

    def is_missing(self) -> bool:
        return (
            not self.content
            or self.content.strip().lower() in ("not mentioned", "not provided", "n/a", "")
        )


@dataclass
class GradProgram:
    """研究生项目统一数据模型。"""
    # 元数据
    source_file: str
    country: Country
    school: str
    program_name: str
    degree: DegreeType
    major_direction: MajorDirection

    # 13 个标准字段
    application_materials: FieldEntry
    interview_requirements: FieldEntry
    application_deadlines: FieldEntry
    academic_requirements: FieldEntry
    gre_gmat_requirements: FieldEntry
    english_proficiency_requirements: FieldEntry
    program_overview: FieldEntry
    curriculum: FieldEntry
    cost_of_attendance: FieldEntry
    financial_aid: FieldEntry
    multiple_applications: FieldEntry
    deferral_admission_policy: FieldEntry
    conditional_admission_policy: FieldEntry

    # 清洗标记
    missing_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        """唯一标识: school-degree-program"""
        return f"{self.school}-{self.degree.value}-{self.program_name}"

    @property
    def display_name(self) -> str:
        return f"{self.program_name} ({self.degree.value}) - {self.school}"

    def to_dict(self) -> dict:
        """输出为可序列化 dict。"""
        d = asdict(self)
        d["country"] = self.country.value
        d["degree"] = self.degree.value
        d["major_direction"] = self.major_direction.value
        return d


# ── 文件名解析 ────────────────────────────────────────────

# e.g. "Business Analytics_MSc_UCL.json" or "Marketing Analytics and Insights_M.Sc._NUS.json"
FILENAME_RE = re.compile(
    r"^(?P<program>.+?)_"
    r"(?P<degree>MSc|M\.Sc\.|MA|MSA|MBA|MBAI|LLM|JD|MiM|MPA|MSE|MQF|MSFE|MEI|MITB|"
    r"MAA|MDS|MSocSc|MTech|MST|MDSE|Msc|Master)"
    r"_(?P<school>[A-Za-z]+(?:\s*\([^)]*\))?)"
    r"\.json$"
)

# "Master" 在文件名中作为 MSc 的泛称 → 规范化为 MSc
MASTER_ALIASES = {"Master", "Msc"}

def parse_filename(filename: str) -> dict:
    """从文件名提取 program_name, degree, school。"""
    m = FILENAME_RE.match(filename)
    if not m:
        raise ValueError(f"Cannot parse filename: {filename}")
    return {
        "program_name": m.group("program").strip(),
        "degree_raw": m.group("degree").strip(),
        "school_raw": m.group("school").strip(),
    }


def classify_direction(program_name: str) -> MajorDirection:
    """根据专业名匹配专业方向。"""
    lower = program_name.lower()
    for direction, keywords in DIRECTION_KEYWORDS:
        for kw in keywords:
            if kw in lower:
                return direction
    return MajorDirection.GENERAL


# ── 数据加载与校验 ────────────────────────────────────────

def load_raw_json(filepath: str) -> dict:
    """加载原始 JSON 文件并返回 {field_name: FieldEntry}。"""
    with open(filepath, "r", encoding="utf-8") as f:
        raw = json.load(f)
    result = {}
    for field_name in STD_FIELDS:
        entry = raw.get(field_name, {"url": "", "content": ""})
        result[field_name] = FieldEntry.from_dict(entry)
    return result


def build_program(filepath: str, skip_duplicates: bool = True) -> GradProgram:
    """从单个 JSON 文件构建 GradProgram 对象。"""
    filename = os.path.basename(filepath)
    meta = parse_filename(filename)

    # 规范化学位
    degree = normalize_degree(meta["degree_raw"])
    school = meta["school_raw"]

    # 确定国家
    country = SCHOOL_COUNTRY.get(school)
    if country is None:
        raise ValueError(f"Unknown school '{school}', cannot determine country. "
                         f"Add to SCHOOL_COUNTRY mapping.")

    # 确定专业方向
    program_name = meta["program_name"]
    major_direction = classify_direction(program_name)

    # 加载字段
    fields = load_raw_json(filepath)

    # 缺失字段检测
    missing = [name for name, entry in fields.items() if entry.is_missing()]

    return GradProgram(
        source_file=filename,
        country=country,
        school=school,
        program_name=program_name,
        degree=degree,
        major_direction=major_direction,
        application_materials=fields["Application Materials"],
        interview_requirements=fields["Interview Requirements"],
        application_deadlines=fields["Application Deadlines"],
        academic_requirements=fields["Academic Requirements"],
        gre_gmat_requirements=fields["GRE GMAT Requirements"],
        english_proficiency_requirements=fields["English Proficiency Requirements"],
        program_overview=fields["Program Overview"],
        curriculum=fields["Curriculum"],
        cost_of_attendance=fields["Cost of Attendance"],
        financial_aid=fields["Financial Aid"],
        multiple_applications=fields["Multiple Applications"],
        deferral_admission_policy=fields["Deferral Admission Policy"],
        conditional_admission_policy=fields["Conditional Admission Policy"],
        missing_fields=missing,
    )


def load_all_programs(analytics_dir: str, smu_dir: str) -> list[GradProgram]:
    """加载所有研究生项目数据，返回 GradProgram 列表。"""
    programs = []
    errors = []

    for directory in [analytics_dir, smu_dir]:
        if not os.path.isdir(directory):
            errors.append(f"Directory not found: {directory}")
            continue
        for filename in sorted(os.listdir(directory)):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(directory, filename)
            try:
                prog = build_program(filepath)
                programs.append(prog)
            except Exception as e:
                errors.append(f"{filename}: {e}")

    if errors:
        print(f"[WARN] {len(errors)} file(s) failed to parse:")
        for err in errors:
            print(f"  - {err}")

    return programs


def check_duplicates(programs: list[GradProgram]) -> list[tuple[GradProgram, GradProgram]]:
    """检测重复项目 (同学校 + 同专业名 + 同学位)。"""
    seen = {}
    dups = []
    for p in programs:
        key = (p.school.lower(), p.program_name.lower(), p.degree.value.lower())
        if key in seen:
            dups.append((seen[key], p))
        else:
            seen[key] = p
    return dups


def validate_urls(programs: list[GradProgram]) -> list[str]:
    """校验所有 URL 的有效性 (格式层面)。"""
    issues = []
    field_names = STD_FIELDS
    for p in programs:
        for fname in field_names:
            entry = getattr(p, fname.lower().replace(" ", "_"))
            url = entry.url.strip()
            if url:
                parsed = urlparse(url)
                if not parsed.scheme or not parsed.netloc:
                    issues.append(f"{p.source_file}/{fname}: invalid URL '{url}'")
    return issues


# ── SMU.xlsx 解析 ─────────────────────────────────────────

@dataclass
class SMUXlsxRow:
    """SMU.xlsx 单行数据。"""
    program: str
    degree: str
    level: str           # "master"
    university: str
    school_dept: str     # 所属学院
    duration: str
    application_fee: str
    tuition: str
    portal_url: str
    info_url_primary: str
    info_url_secondary: str

    def to_field_entry(self, content: str, url: str = "") -> FieldEntry:
        return FieldEntry(url=url, content=content)

    def to_grad_program(self) -> GradProgram:
        """将 xlsx 行转为 GradProgram(精简版，大部分字段标记为缺失)。"""
        country = SCHOOL_COUNTRY.get(self.university, Country.SG)
        degree = normalize_degree(self.degree.replace(" ", ""))
        direction = classify_direction(self.program)

        # 构建可用字段内容
        duration_info = f"Duration: {self.duration}"
        fee_info = f"Application Fee: {self.application_fee}\nTuition: {self.tuition}"
        dept_info = f"School/Department: {self.school_dept}"

        empty = FieldEntry(url="", content="Not Mentioned")

        missing = [
            "Application Materials", "Interview Requirements",
            "Academic Requirements", "GRE GMAT Requirements",
            "English Proficiency Requirements",
            "Financial Aid", "Multiple Applications",
            "Deferral Admission Policy", "Conditional Admission Policy",
        ]

        return GradProgram(
            source_file=f"SMU.xlsx::{self.program}",
            country=country,
            school=self.university,
            program_name=self.program,
            degree=degree,
            major_direction=direction,
            application_materials=empty,
            interview_requirements=empty,
            application_deadlines=FieldEntry(url=self.portal_url,
                content=f"Application Portal: {self.portal_url}"),
            academic_requirements=empty,
            gre_gmat_requirements=empty,
            english_proficiency_requirements=empty,
            program_overview=FieldEntry(
                url=self.info_url_primary or self.info_url_secondary,
                content=f"{dept_info}\n{duration_info}"),
            curriculum=empty,
            cost_of_attendance=FieldEntry(url="", content=fee_info),
            financial_aid=empty,
            multiple_applications=empty,
            deferral_admission_policy=empty,
            conditional_admission_policy=empty,
            missing_fields=missing,
        )


def parse_smu_xlsx(filepath: str) -> list[SMUXlsxRow]:
    """解析 SMU.xlsx 返回结构化行列表。"""
    try:
        import openpyxl
    except ImportError:
        raise ImportError("openpyxl required for xlsx parsing. pip install openpyxl")

    wb = openpyxl.load_workbook(filepath, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(min_row=2, values_only=True))  # skip header
    wb.close()

    result = []
    for row in rows:
        if not row[0]:  # skip empty rows
            continue
        result.append(SMUXlsxRow(
            program=str(row[0]).strip() if row[0] else "",
            degree=str(row[1]).strip() if row[1] else "",
            level=str(row[2]).strip() if row[2] else "master",
            university=str(row[3]).strip() if row[3] else "SMU",
            school_dept=str(row[4]).strip() if row[4] else "",
            duration=str(row[5]).strip() if row[5] else "",
            application_fee=str(row[6]).strip() if row[6] else "",
            tuition=str(row[7]).strip() if row[7] else "",
            portal_url=str(row[8]).strip() if row[8] else "",
            info_url_primary=str(row[9]).strip() if row[9] else "",
            info_url_secondary=str(row[10]).strip() if row[10] else "",
        ))
    return result


def enrich_smu_programs(programs: list[GradProgram], xlsx_path: str) -> list[GradProgram]:
    """用 SMU.xlsx 的元数据补充 SMU 项目的 duration/tuition/fee 信息。"""
    try:
        xlsx_rows = parse_smu_xlsx(xlsx_path)
    except Exception as e:
        print(f"[WARN] Cannot parse {xlsx_path}: {e}")
        return programs

    # 按 program_name + degree 建索引
    xlsx_index = {}
    for row in xlsx_rows:
        try:
            deg = normalize_degree(row.degree.replace(" ", ""))
        except ValueError:
            deg = None
        key = (row.program.lower(), deg.value.lower() if deg else row.degree.lower())
        xlsx_index[key] = row

    enriched = 0
    for p in programs:
        if p.school != "SMU":
            continue
        key = (p.program_name.lower(), p.degree.value.lower())
        row = xlsx_index.get(key)
        if not row:
            # 模糊匹配
            for k, v in xlsx_index.items():
                if p.program_name.lower() in k[0] or k[0] in p.program_name.lower():
                    row = v
                    break
        if row:
            # 补充 duration / tuition 信息到 Program Overview 和 Cost of Attendance
            duration_info = f"\nDuration: {row.duration}"
            fee_info = (f"Application Fee: {row.application_fee}\n"
                        f"Tuition: {row.tuition}")

            if duration_info not in p.program_overview.content:
                p.program_overview.content += duration_info
            if row.tuition and "Not Mentioned" in p.cost_of_attendance.content:
                p.cost_of_attendance.content = fee_info
                p.cost_of_attendance.url = row.info_url_primary or row.info_url_secondary
            enriched += 1

    print(f"[INFO] Enriched {enriched} SMU program(s) with xlsx metadata.")
    return programs


# ── 汇总报告 ──────────────────────────────────────────────

def summary(programs: list[GradProgram]) -> str:
    lines = [
        f"Total programs: {len(programs)}",
        f"Countries: {Counter(p.country.value for p in programs)}",
        f"Schools: {Counter(p.school for p in programs)}",
        f"Degrees: {Counter(p.degree.value for p in programs)}",
        f"Directions: {Counter(p.major_direction.value for p in programs)}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    from collections import Counter

    BASE = Path(__file__).resolve().parent.parent
    analytics = str(BASE / "Analytics")
    smu = str(BASE / "SMU")
    smu_xlsx = str(BASE / "SMU" / "SMU.xlsx")

    programs = load_all_programs(analytics, smu)

    # SMU.xlsx 补充元数据
    if os.path.exists(smu_xlsx):
        programs = enrich_smu_programs(programs, smu_xlsx)

    # 汇总
    print(summary(programs))
    print()

    # 缺失字段
    missing_count = Counter()
    for p in programs:
        for mf in p.missing_fields:
            missing_count[mf] += 1
    if missing_count:
        print("Missing fields:")
        for k, c in missing_count.most_common():
            print(f"  {k}: {c} project(s)")
    else:
        print("No missing fields detected.")

    # 去重
    dups = check_duplicates(programs)
    if dups:
        print(f"\nWARNING: {len(dups)} duplicate pair(s):")
        for a, b in dups:
            print(f"  - {a.source_file}  <=>  {b.source_file}")
    else:
        print("\nNo duplicates found.")

    # URL 校验
    url_issues = validate_urls(programs)
    if url_issues:
        print(f"\nURL issues ({len(url_issues)}):")
        for issue in url_issues:
            print(f"  - {issue}")
    else:
        print("\nAll URLs pass format validation.")

    # 输出 enriched JSON
    out_path = str(BASE / "output" / "grad_programs_enriched.json")
    os.makedirs(str(BASE / "output"), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump([p.to_dict() for p in programs], f, ensure_ascii=False, indent=2)
    print(f"\nEnriched data written to {out_path}")

    # 输出数据质量报告
    report_lines = [
        "# D1 研究生数据结构化 — 数据质量报告",
        "",
        summary(programs),
        "",
        "## 缺失字段统计",
    ]
    for k, c in missing_count.most_common():
        report_lines.append(f"- {k}: {c} 项目 ({c/len(programs)*100:.1f}%)")
    report_lines.append("")
    report_lines.append("## SMU.xlsx 元数据")
    xlsx_rows = parse_smu_xlsx(smu_xlsx) if os.path.exists(smu_xlsx) else []
    report_lines.append(f"- 共 {len(xlsx_rows)} 条 SMU 项目元数据")
    report_lines.append(f"- 字段: program, degree, school_dept, duration, "
                         f"application_fee, tuition, portal_url")
    report_path = str(BASE / "output" / "D1_data_quality_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    print(f"Quality report written to {report_path}")
