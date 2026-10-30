"""Source-aligned query sections, independent of embedding/index signatures.

Headings may be inline or broken across lines. Unheaded text is kept as unknown;
neither the title nor a keyword is sufficient to assert its business role.
"""
import re

SECTION_RULE_VERSION = "query-sections-v1"
SECTION_TYPES = ("responsibilities", "requirements", "preferred", "company_intro", "benefits", "unknown")
HEADINGS = {
    "responsibilities": ["岗位职责", "工作职责", "职位职责", "工作内容", "主要职责", "核心职责", "职责描述",
        "你将负责", "你将具体负责", "你要负责什么", "你每天会做的事", "你会做什么", "你会做", "你将面对的挑战",
        "职位描述", "岗位描述", "工作范围", "岗位职能", "岗位工作范围和职责", "这个岗位做什么",
        "Roles and Responsibilities", "Major Responsibilities", "Responsibilities", "Job Description"],
    "requirements": ["任职要求", "任职资格", "岗位要求", "职位要求", "任职条件", "基本要求", "基础任职要求",
        "工作要求", "硬性要求", "职责要求", "核心要求", "必备技能", "必备工作经验", "技能要求", "核心技术",
        "我们希望你具备", "我们希望你", "我们希望您", "我们期待你", "我们想要的你", "我们需要这样的你",
        "你需要具备", "需要的技能", "Minimum Job Requirements", "Job Requirements", "Requirements", "Qualifications"],
    "preferred": ["加分项", "加分条件", "优先条件", "加分技能", "Preferred Qualifications", "Nice to have"],
    "company_intro": ["公司介绍", "关于我们", "企业介绍", "我们是谁", "岗位介绍", "岗位概述", "职位概述", "岗位背景"],
    "benefits": ["福利待遇", "薪资福利", "我们提供", "为什么选择我们", "加入我们", "工作方式", "岗位说明"],
}
LOOKUP = {re.sub(r"\s", "", title).casefold(): kind for kind, titles in HEADINGS.items() for title in titles}


def _pattern(title):
    if re.search(r"[\u4e00-\u9fff]", title):
        return r"\s*".join(re.escape(c) for c in title)
    return r"(?<![A-Za-z])" + r"\s+".join(re.escape(w) for w in title.split()) + r"(?![A-Za-z])"


HEADING = re.compile("|".join(_pattern(title) for title in sorted(
    [t for titles in HEADINGS.values() for t in titles], key=len, reverse=True)), re.I)
# Short generic headings require a line start and punctuation or a line break.
SHORT = re.compile(r"^[ \t]*(?:[【\[])?(?P<title>职责|要求|加分)[】\]]?[ \t]*(?:[:：]|\r?$)", re.M)


def parse_query_sections(description):
    headings = [(m.start(), m.end(), m.group(), LOOKUP[re.sub(r"\s", "", m.group()).casefold()])
                for m in HEADING.finditer(description)
                if m.start() == 0 or description[m.start() - 1].isspace()
                or description[m.start() - 1] in "【[：:。；;、）)▶▍◆■*#|-•，,"]
    for match in SHORT.finditer(description):
        if not any(start <= match.start() < end for start, end, _, _ in headings):
            headings.append((match.start(), match.end(), match["title"],
                             {"职责": "responsibilities", "要求": "requirements", "加分": "preferred"}[match["title"]]))
    headings.sort()
    sections = []
    if not headings or headings[0][0] > 0:
        sections.append({"section_type": "unknown", "title": "未明确分节", "source_start": 0,
                         "source_end": headings[0][0] if headings else len(description)})
    for i, (start, end, title, kind) in enumerate(headings):
        sections.append({"section_type": kind, "title": title, "heading_start": start, "heading_end": end,
                         "source_start": end, "source_end": headings[i + 1][0] if i + 1 < len(headings) else len(description)})
    for i, section in enumerate(sections):
        section.update(section_id=f"section-{i}", text=description[section["source_start"]:section["source_end"]],
                       classification="rule_derived", rule_version=SECTION_RULE_VERSION)
    return sections


def section_coverage(sections):
    meaningful = [s for s in sections if s["text"].strip()]
    return {"section_rule_version": SECTION_RULE_VERSION,
            "known_characters": sum(len(s["text"]) for s in meaningful if s["section_type"] != "unknown"),
            "unknown_characters": sum(len(s["text"]) for s in meaningful if s["section_type"] == "unknown"),
            "has_unknown_text": any(s["section_type"] == "unknown" for s in meaningful),
            "has_recognized_sections": any(s["section_type"] != "unknown" for s in meaningful)}
