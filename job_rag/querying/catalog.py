"""Exhaustive literal catalog queries with optional source-aligned section scope."""
import re
from collections import Counter
from dataclasses import dataclass
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from ..preprocessing.normalize import digest
from ..storage.serialization import serialize
from .filters import StructuredFilters, matches
from .catalog_snapshot import SnapshotChanged, load_catalog, eligible_jobs
from .sections import SECTION_RULE_VERSION, parse_query_sections
from .conditions import evidence_item

SectionType = Literal["responsibilities", "requirements", "preferred", "company_intro", "benefits", "unknown"]


class CatalogRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    terms: list[str] = Field(default_factory=list, max_length=20)
    fields: list[Literal["title", "description"]] = Field(default_factory=lambda: ["title", "description"], min_length=1)
    operator: Literal["and", "or"] = "and"
    case_sensitive: bool = False
    match_mode: Literal["substring", "token", "ascii_token"] = "substring"
    aliases: dict[str, list[str]] = Field(default_factory=dict, max_length=20)
    sections: list[SectionType] | None = Field(default=None, min_length=1)
    include_preferred: bool = False
    evidence_limit: int = Field(default=8, ge=1, le=40)
    filters: StructuredFilters = Field(default_factory=StructuredFilters)
    page_size: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    snapshot_id: str | None = None
    count_only: bool = False

    @model_validator(mode="after")
    def validate_query(self):
        if any(not term.strip() or len(term) > 200 for term in self.terms):
            raise ValueError("Terms must be nonblank and at most 200 characters")
        if set(self.aliases) - set(self.terms):
            raise ValueError("Aliases must belong to explicit query terms")
        if any(len(values) > 10 or any(not value.strip() or len(value) > 200 for value in values)
               for values in self.aliases.values()):
            raise ValueError("Each term allows at most 10 nonblank aliases, each at most 200 characters")
        if self.sections is not None:
            if "fields" not in self.model_fields_set:
                self.fields = ["description"]
            if self.fields != ["description"]:
                raise ValueError("Section queries only support fields=[description]")
        if self.include_preferred and self.sections is None:
            raise ValueError("include_preferred requires explicit sections")
        if self.offset and not self.snapshot_id:
            raise ValueError("Continuation requires snapshot_id")
        if self.filters.active_only and self.filters.include_closed:
            raise ValueError("active_only and include_closed conflict")
        return self


@dataclass(frozen=True)
class LiteralSpan:
    left: int
    right: int

    def start(self):
        return self.left

    def end(self):
        return self.right


def literal_spans(text, term, request):
    # Preserve the old casefold matching contract while mapping expanding folds
    # (e.g. ß -> ss) back to exact original-description character offsets.
    positions = None
    if not request.case_sensitive:
        folded, positions = [], []
        for index, char in enumerate(text):
            value = char.casefold()
            folded.append(value)
            positions.extend([index] * len(value))
        text, term = "".join(folded), term.casefold()
    pattern = re.escape(term)
    if request.match_mode == "token":
        pattern = r"(?<!\w)" + pattern + r"(?!\w)"
    elif request.match_mode == "ascii_token":
        pattern = r"(?<![A-Za-z0-9_])" + pattern + r"(?![A-Za-z0-9_])"
    matches_found = list(re.finditer(pattern, text))
    if positions is None:
        return matches_found
    return [LiteralSpan(positions[m.start()], positions[m.end() - 1] + 1) for m in matches_found]


def literal_hit(text, term, request):
    return bool(literal_spans(text, term, request))


def _hits(parts, request):
    values = [any(literal_hit(part, spelling, request) for part in parts
                  for spelling in [term] + request.aliases.get(term, [])) for term in request.terms]
    return not values or (all(values) if request.operator == "and" else any(values))


def job_matches(job, request):
    description = job.raw.get("description", "")
    sections = parse_query_sections(description)
    selected_types = set(request.sections or []) | ({"preferred"} if request.include_preferred else set())
    selected = [s for s in sections if s["section_type"] in selected_types]
    parts = [s["text"] for s in selected] if request.sections is not None else [job.raw.get(f, "") for f in request.fields]
    match = _hits(parts, request)
    unknown = [s for s in sections if s["section_type"] == "unknown" and s["text"].strip()]
    unknown_parts = [s["text"] for s in unknown]
    unknown_hit = bool(unknown) and (_hits(unknown_parts, request)
        or (not match and _hits(parts + unknown_parts, request)))
    preferred = [s for s in sections if s["section_type"] == "preferred"]
    preferred_hit = bool(preferred) and _hits([s["text"] for s in preferred], request)
    evidence = []
    # Evidence records always refer to original description character offsets.
    for section in selected if request.sections is not None else sections:
        for term in request.terms:
            for spelling in [term] + request.aliases.get(term, []):
                for found in literal_spans(section["text"], spelling, request):
                    start = section["source_start"] + found.start()
                    end = section["source_start"] + found.end()
                    evidence.append({**evidence_item(description, section, start, end),
                                     "query_term": term, "matched_alias": spelling})
    return match, sections, evidence, unknown_hit, preferred_hit


def scan_catalog(db, request):
    jobs, corpus_id = load_catalog(db)
    criteria = request.model_dump(exclude={"page_size", "offset", "snapshot_id", "count_only", "evidence_limit",
                                          "include_details", "evidence_samples_per_technology", "corpus_id"})
    snapshot_id = digest({"contract": "section-literal-v2", "parser": SECTION_RULE_VERSION,
                          "corpus": corpus_id, "criteria": criteria})
    if request.snapshot_id and request.snapshot_id != snapshot_id:
        raise SnapshotChanged("数据或查询条件发生变化；请从第一页重新开始，不得合并旧统计。")
    eligible = eligible_jobs(jobs, request.filters)
    selected, unknown, preferred = [], [], []
    for job in eligible:
        matched, sections, evidence, unknown_hit, preferred_hit = job_matches(job, request)
        record = (job, sections, evidence)
        if matched:
            selected.append(record)
        if request.sections is not None and unknown_hit:
            unknown.append({**serialize(job), "also_matched_known_sections": matched})
        if request.sections is not None and preferred_hit and not matched:
            preferred.append(serialize(job))
    unresolved = [j for j in unknown if not j["also_matched_known_sections"]]
    metadata = {"snapshot_id": snapshot_id, "corpus_id": corpus_id, "snapshot_policy": "restart_on_change",
        "scope": criteria, "section_rule_version": SECTION_RULE_VERSION,
        "corpus_jobs": len(jobs), "eligible_jobs": len(eligible),
        "eligible_statuses": dict(Counter(j.job_status for j in eligible)),
        "missing_description_jobs": sum(not j.raw.get("description", "").strip() for j in eligible),
        "matched_jobs": len(selected), "count_kind": "exact_section_literal_under_rules" if request.sections else "exact_literal_not_semantic",
        "count_complete": True, "semantic_count_complete": False,
        "section_scope_complete": not unresolved,
        "unknown_match_jobs": len(unknown), "unresolved_jobs": len(unresolved),
        "unknown_match_sample": unknown[:20], "unknown_sample_truncated": len(unknown) > 20,
        "preferred_only_match_jobs": len(preferred), "preferred_only_sample": preferred[:20],
        "processed_jobs": len(eligible), "unprocessed_jobs": 0,
        "deduplication": "source_and_job_id", "index_required": False,
        "warnings": ["unknown 是未核验，不代表在招；字面出现不代表必备条件。",
                     "章节与条件标签均为规则派生；未识别章节的岗位单列，不能当作不符合。"]}
    return selected, metadata


def catalog_query(db, request):
    selected, metadata = scan_catalog(db, request)
    page = [] if request.count_only else selected[request.offset:request.offset + request.page_size]
    results = []
    for job, sections, evidence in page:
        record = serialize(job)
        record.update(match_evidence=evidence[:request.evidence_limit],
                      match_evidence_truncated=len(evidence) > request.evidence_limit,
                      evidence_total=len(evidence))
        results.append(record)
    next_offset = request.offset + len(page)
    has_more = not request.count_only and next_offset < len(selected)
    return {**metadata, "results": results, "offset": request.offset,
            "next_offset": next_offset if has_more else None, "has_more": has_more}


# Existing Python callers keep working; each tool's implementation is separate.
from .get_jobs_batch import BatchRequest, JobRef, batch_jobs
