"""Source-aligned, conservative recruitment document segmentation.

Structural/condition labels are derived annotations, never rewritten source text.
Unknown and mixed conditions are explicit rather than guessed into requirements.
"""
from dataclasses import dataclass
import re

PARSER_VERSION = "headings-items-v1"
CHUNKING_VERSION = "sections-v1"
STRATEGIES = ("legacy", "fixed_compact", "section_compact", "section_typed")
SECTION_NAMES = {
    "岗位职责": "responsibilities", "工作职责": "responsibilities", "职位职责": "responsibilities",
    "工作内容": "responsibilities", "主要职责": "responsibilities", "你将负责": "responsibilities",
    "核心职责": "responsibilities", "岗位描述": "unknown",
    "你会做什么": "responsibilities", "你将参与的核心项目": "responsibilities", "职位描述": "unknown",
    "任职要求": "requirements", "任职资格": "requirements", "岗位要求": "requirements",
    "职位要求": "requirements", "任职条件": "requirements", "我们希望你": "requirements",
    "工作要求": "requirements", "硬性要求": "requirements", "基本要求": "requirements", "职责要求": "requirements",
    "你需要具备": "requirements", "要求": "requirements", "同时我们还希望你": "requirements",
    "加分项": "preferred", "加分条件": "preferred", "优先条件": "preferred", "优先考虑": "preferred",
    "优先考虑条件（加分项）": "preferred",
    "福利待遇": "benefits", "薪资福利": "benefits", "我们提供": "benefits", "福利": "benefits",
    "公司介绍": "company_intro", "关于我们": "company_intro", "企业介绍": "company_intro",
    "我们是谁": "company_intro",
}
HEADING = re.compile(
    r"^[ \t]*(?:[▍▶►◆■]+[ \t]*)?(?:#{1,6}[ \t]*)?(?:[一二三四五六七八九十\d]+[、.．）)][ \t]*)?"
    r"(?:\*\*)?[【\[]?(?P<title>" +
    "|".join(r"\s*".join(re.escape(char) for char in title) for title in sorted(SECTION_NAMES, key=len, reverse=True)) +
    r")[】\]]?(?:\*\*)?[ \t]*(?:[（(][^）)\r\n]{0,50}[）)][ \t]*)?(?:[:：](?:\*\*)?[ \t]*|\r?$)", re.M
)
PREFERRED = re.compile(r"优先|加分|更佳|更好|优选|preferred|nice\s+to\s+have", re.I)
NEGATIVE = re.compile(r"不(?:强制)?要求|无需|不必|不限(?:经验|学历)|非必[须备]|not\s+required", re.I)
EXPLICIT = re.compile(r"必须|必备|须具备|要求具备|但需|但要求|仍需|同时需|mandatory|required", re.I)
EXCEPTION = re.compile(r"可放宽|可适当放宽|优秀者|或者|或具备|满足其一|二者之一")


@dataclass(frozen=True)
class Section:
    section_id: str
    section_type: str
    title: str
    start: int
    end: int
    heading_start: int | None
    heading_end: int | None


@dataclass(frozen=True)
class Document:
    text: str
    details: dict


class Budget:
    """Explicit units: chars, utf8_bytes, or an explicitly supplied local tokenizer.

    Neither chars nor byte counts are reported as provider token counts. The hosted
    Qwen3.7 tokenizer has not been assumed equivalent to an older Qwen tokenizer.
    """
    def __init__(self, kind="chars", tokenizer_path=""):
        self.kind = kind
        self.tokenizer = None
        if kind == "tokens":
            if not tokenizer_path:
                raise ValueError("tokens budget requires a verified local tokenizer JSON path")
            from tokenizers import Tokenizer
            self.tokenizer = Tokenizer.from_file(tokenizer_path)
        elif kind not in {"chars", "utf8_bytes"}:
            raise ValueError("Unknown budget unit")

    def count(self, text):
        if self.kind == "tokens":
            return len(self.tokenizer.encode(text, add_special_tokens=True).ids)
        return len(text.encode("utf-8")) if self.kind == "utf8_bytes" else len(text)


def parse_sections(description):
    headings = []
    for match in HEADING.finditer(description):
        title = re.sub(r"\s", "", match["title"])
        headings.append((match.start(), match.end(), title, SECTION_NAMES[title]))
    sections = []
    if not headings or headings[0][0] > 0:
        end = headings[0][0] if headings else len(description)
        sections.append(Section("section-0", "unknown", "未明确分节", 0, end, None, None))
    for i, (start, end, title, section_type) in enumerate(headings):
        body_end = headings[i + 1][0] if i + 1 < len(headings) else len(description)
        sections.append(Section(f"section-{len(sections)}", section_type, title, end, body_end, start, end))
    return sections


def condition_level(text, section_type):
    # Negative and positive qualifications in one item cannot safely share a label.
    if section_type in {"responsibilities", "benefits", "company_intro"}:
        return "unspecified"
    preferred, negative = bool(PREFERRED.search(text)), bool(NEGATIVE.search(text))
    required = bool(EXPLICIT.search(NEGATIVE.sub("", text)))
    if preferred:
        clauses = re.split(r"[，,。；;]", text)
        if len(clauses) > 1 and any(clause.strip() and not PREFERRED.search(clause) and not NEGATIVE.search(clause)
                                    for clause in clauses[:-1]):
            return "mixed"
    if EXCEPTION.search(text) or sum([preferred, negative, required]) > 1:
        return "mixed"
    if negative:
        return "not_required"
    if preferred or section_type == "preferred":
        # A preferred heading remains the scope even if an item uses 'required'.
        return "mixed" if required else "preferred"
    if required or section_type == "requirements":
        return "required"
    return "unspecified"


def item_spans(text, start, end):
    """A numbered/bulleted item includes continuation lines; unnumbered text uses lines."""
    body = text[start:end]
    bullets = list(re.finditer(r"(?m)^\s*(?:\d+[.．、）)]|[①②③④⑤⑥⑦⑧⑨⑩]|[-•●])\s*", body))
    boundaries = [start]
    if bullets:
        boundaries.extend(start + match.start() for match in bullets if match.start() > 0)
    else:
        boundaries.extend(start + match.end() for match in re.finditer(r"\n", body) if match.end() < len(body))
    boundaries.append(end)
    return [(a, b) for a, b in zip(boundaries, boundaries[1:]) if text[a:b].strip()]


def _header(row, section=None, level="unspecified", typed=True):
    header = f"岗位：{row.get('title', '')}\n"
    if section:
        header += f"章节：{section.title}\n"
        if typed:
            labels = {"required": "任职要求（保留原文中的或关系、否定和例外）", "preferred": "优先/加分条件，非明确必备",
                      "not_required": "明确不要求", "mixed": "混合或带例外条件，请逐句核对", "unspecified": "未明确条件性质"}
            header += f"条件性质：{labels[level]}\n"
    return header + "原文：\n"


def _legacy_spans(row, size):
    from .normalize import legacy_documents
    position = 0
    for rendered in legacy_documents(row, size):
        body = rendered.split("\n\n", 1)[1]
        start = row["description"].find(body, position)
        if start < 0:
            raise ValueError("Legacy chunk is not aligned with source")
        end = start + len(body)
        yield rendered, start, end
        position = end


def _split_long(text, start, end, fits):
    """Prefer complete sentences; hard splits explicitly retain item provenance."""
    sentence_ends = [start + match.end() for match in re.finditer(r"[。！？；;](?:\s|$)?", text[start:end])]
    position = start
    while position < end:
        if fits(text[position:end]):
            yield position, end, position != start and position not in sentence_ends
            break
        # Binary search gives an initial prefix; trim until the chosen tokenizer fits.
        lo, hi = position, end
        while lo < hi:
            middle = (lo + hi + 1) // 2
            if fits(text[position:middle]):
                lo = middle
            else:
                hi = middle - 1
        candidates = [boundary for boundary in sentence_ends if position < boundary <= lo]
        cut = max(candidates) if candidates else lo
        while cut > position and not fits(text[position:cut]):
            cut -= 1
        if cut <= position:
            raise ValueError("Chunk budget is too small for header and source character")
        hard = cut not in sentence_ends or (position != start and position not in sentence_ends)
        yield position, cut, hard
        position = cut


def build_documents(row, strategy="section_typed", size=1100, budget_kind="chars", tokenizer_path=""):
    if strategy not in STRATEGIES:
        raise ValueError("Unknown chunking strategy")
    if size < 64:
        raise ValueError("Chunk budget must be at least 64")
    description = row.get("description", "")
    if not description.strip():
        return []
    budget = Budget(budget_kind, tokenizer_path)
    if strategy in {"legacy", "fixed_compact"}:
        if budget_kind != "chars":
            raise ValueError("Legacy-aligned controls use character budgets, not token estimates")
        output = []
        for original, start, end in _legacy_spans(row, size):
            text = original if strategy == "legacy" else _header(row) + description[start:end]
            hard = (start > 0 and description[start - 1] != "\n") or (end < len(description) and description[end - 1] != "\n")
            output.append(Document(text, {"raw_text": description[start:end], "source_start": start, "source_offset_unit": "unicode_codepoints",
                "source_end": end, "section_type": "unknown", "section_title": "未解析", "requirement_level": "unspecified",
                "section_id": None, "item_spans": [], "hard_split": hard, "strategy": strategy,
                "parser_version": "legacy", "chunking_version": "document-v1", "budget_unit": "chars",
                "budget_size": size, "rendered_units": budget.count(text)}))
        return output
    output = []
    for section in parse_sections(description):
        buffer = None

        def emit(entry):
            start, end, level, items, hard = entry
            raw = description[start:end]
            text = _header(row, section, level, typed=strategy == "section_typed") + raw
            output.append(Document(text, {"raw_text": raw, "source_start": start, "source_end": end, "source_offset_unit": "unicode_codepoints",
                "section_type": section.section_type, "section_title": section.title, "section_id": section.section_id,
                "section_start": section.start, "section_end": section.end,
                "heading_start": section.heading_start, "heading_end": section.heading_end,
                "requirement_level": level, "label_method": "conservative_rules", "item_spans": items,
                "hard_split": hard, "strategy": strategy, "parser_version": PARSER_VERSION,
                "chunking_version": CHUNKING_VERSION, "budget_unit": budget.kind, "budget_size": size,
                "rendered_units": budget.count(text)}))

        for item_start, item_end in item_spans(description, section.start, section.end):
            level = condition_level(description[item_start:item_end], section.section_type)
            # Compact/typed structural arms reserve identical headers so boundaries match.
            fits = lambda raw: budget.count(_header(row, section, level, typed=True) + raw) <= size
            for start, end, hard in _split_long(description, item_start, item_end, fits):
                item = {"start": item_start, "end": item_end, "continuation_id": f"item-{item_start}-{item_end}"}
                if buffer and buffer[2] == level and not hard and not buffer[4] and fits(description[buffer[0]:end]):
                    buffer = (buffer[0], end, level, buffer[3] + [item], False)
                else:
                    if buffer:
                        emit(buffer)
                    buffer = (start, end, level, [item], hard)
        if buffer:
            emit(buffer)
    return output
