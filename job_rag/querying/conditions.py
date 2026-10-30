"""Conservative condition annotations; these are rules, not verified skill facts."""
import re

CONDITION_RULE_VERSION = "qualification-rules-v1"
PREFERRED = re.compile(r"优先|加分|更佳|更好|preferred|nice\s+to\s+have", re.I)
NEGATIVE = re.compile(r"不(?:强制)?要求|无需|不必|非必[须备]|not\s+required", re.I)
REQUIRED = re.compile(r"必须|必备|须具备|要求具备|但需|仍需|mandatory|\brequired\b", re.I)
ALTERNATIVE = re.compile(r"或者|或具备|满足其一|二者之一|任选|至少一[种门项个]|\bor\b|或", re.I)


def condition_annotation(text, section_type):
    negative = bool(NEGATIVE.search(text))
    required = bool(REQUIRED.search(NEGATIVE.sub("", text)))
    preferred = section_type == "preferred" or bool(PREFERRED.search(text))
    signals = [name for name, value in [("not_required", negative), ("required", required), ("preferred", preferred)] if value]
    # Negated or preferred siblings in one item remain mixed, rather than assigning
    # their condition to every technology in that item.
    level = "mixed" if len(signals) > 1 else (signals[0] if signals else
            "responsibility" if section_type == "responsibilities" else "unspecified")
    alternative = bool(ALTERNATIVE.search(text))
    return {"requirement_level": level, "alternative": alternative, "signals": signals,
            "assessment_method": "rule_derived", "condition_rule_version": CONDITION_RULE_VERSION,
            "needs_review": level in {"mixed", "unspecified"} or alternative,
            "verified": False}


def evidence_item(description, section, start, end):
    """Keep an entire numbered line/paragraph so alternatives and negation survive."""
    left, right = section["source_start"], section["source_end"]
    before = list(re.finditer(r"[\n;；。]", description[left:start]))
    after = re.search(r"[\n;；。]", description[end:right])
    item_start = left + before[-1].end() if before else left
    item_end = end + after.end() if after else right
    text = description[item_start:item_end]
    return {"section_id": section["section_id"], "section_type": section["section_type"],
            "source_start": item_start, "source_end": item_end, "text": text,
            "match_start": start, "match_end": end, "matched_text": description[start:end],
            **condition_annotation(text, section["section_type"])}
