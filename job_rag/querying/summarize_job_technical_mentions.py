"""Exhaustive job-level technical mention counts, with source evidence and paging."""
import re
from collections import defaultdict
from typing import Literal
from pydantic import Field, model_validator
from ..preprocessing.normalize import digest
from ..storage.serialization import serialize
from .catalog import CatalogRequest, SectionType, scan_catalog
from .catalog_snapshot import SnapshotChanged
from .conditions import CONDITION_RULE_VERSION, evidence_item
from .technical_vocabulary import TECHNOLOGIES, VOCABULARY_VERSION


class TechnicalSummaryRequest(CatalogRequest):
    terms: list[str] = Field(default_factory=lambda: ["RAG"], max_length=20)
    fields: list[Literal["description"]] = Field(default_factory=lambda: ["description"], min_length=1)
    sections: list[SectionType] = Field(default_factory=lambda: ["responsibilities", "requirements"], min_length=1)
    match_mode: Literal["substring", "token", "ascii_token"] = "ascii_token"
    technical_sections: list[SectionType] = Field(default_factory=lambda: ["responsibilities", "requirements"], min_length=1)
    technologies: list[str] | None = Field(default=None, min_length=1, max_length=30)
    corpus_id: str | None = None
    include_details: bool = False
    evidence_samples_per_technology: int = Field(default=2, ge=0, le=5)

    @model_validator(mode="after")
    def validate_summary(self):
        if self.fields != ["description"]:
            raise ValueError("Technical summaries require description fields")
        if self.match_mode not in {"substring", "token", "ascii_token"}:
            raise ValueError("Unsupported match mode")
        if self.technologies is not None and set(self.technologies) - TECHNOLOGIES.keys():
            raise ValueError("Unknown technology category; use the versioned vocabulary")
        return self


def summarize_job_technical_mentions(db, request):
    # Summary pagination is bound to query, vocabulary and condition rules. Source
    # enumeration remains protected by the same corpus fingerprint as catalog.
    selected, metadata = scan_catalog(db, request.model_copy(update={"snapshot_id": None}))
    if request.corpus_id and request.corpus_id != metadata["corpus_id"]:
        raise SnapshotChanged("数据发生变化；请重新枚举后汇总。")
    snapshot_id = digest({"catalog": metadata["snapshot_id"], "vocabulary": VOCABULARY_VERSION,
                          "conditions": CONDITION_RULE_VERSION})
    if request.snapshot_id and request.snapshot_id != snapshot_id:
        raise SnapshotChanged("数据、技术词表或统计条件变化；请从第一页重新开始。")
    names = list(dict.fromkeys(request.technologies or TECHNOLOGIES))
    patterns = {name: re.compile(TECHNOLOGIES[name][1], re.I) for name in names}
    members = {name: set() for name in names}
    conditions = {name: defaultdict(set) for name in names}
    samples = {name: [] for name in names}
    details = []
    unknown_scope_jobs = 0
    allowed_sections = set(request.technical_sections)
    for job, sections, match_evidence in selected:
        description = job.raw.get("description", "")
        unknown_scope_jobs += any(s["section_type"] == "unknown" and s["text"].strip() for s in sections)
        mentions = []
        for name, pattern in patterns.items():
            seen = set()
            for section in sections:
                if section["section_type"] not in allowed_sections:
                    continue
                for found in pattern.finditer(section["text"]):
                    start, end = section["source_start"] + found.start(), section["source_start"] + found.end()
                    evidence = evidence_item(description, section, start, end)
                    identity = (evidence["source_start"], evidence["source_end"], name)
                    if identity in seen:
                        continue
                    seen.add(identity)
                    item = {"technology": name, "job_id": job.job_id, "source": job.source,
                            "key": job.key, "version": job.version, "url": job.raw.get("url", ""), **evidence}
                    mentions.append(item)
                    members[name].add(job.key)
                    conditions[name][item["requirement_level"]].add(job.key)
                    if len(samples[name]) < request.evidence_samples_per_technology and not any(s["key"] == job.key for s in samples[name]):
                        samples[name].append(item)
        details.append({**serialize(job), "technical_mentions": mentions,
                        "match_evidence": match_evidence[:request.evidence_limit],
                        "match_evidence_truncated": len(match_evidence) > request.evidence_limit})
    total = len(selected)
    categories = [{"technology": name, "label": TECHNOLOGIES[name][0], "pattern": TECHNOLOGIES[name][1],
                   "job_count": len(members[name]), "fraction": len(members[name]) / total if total else None,
                   "condition_job_counts": {level: len(keys) for level, keys in conditions[name].items()},
                   "evidence_samples": samples[name]} for name in names]
    categories.sort(key=lambda item: (-item["job_count"], item["technology"]))
    page = details[request.offset:request.offset + request.page_size] if request.include_details and not request.count_only else []
    next_offset = request.offset + len(page)
    has_more = bool(page) and next_offset < total
    return {**metadata, "snapshot_id": snapshot_id, "denominator_jobs": total,
            "vocabulary_version": VOCABULARY_VERSION, "condition_rule_version": CONDITION_RULE_VERSION,
            "analysis_method": "versioned_literal_rules", "semantic_assessment": "not_performed",
            "technical_scope_unknown_jobs": unknown_scope_jobs,
            "technical_sections": request.technical_sections,
            "categories": categories, "details": page, "offset": request.offset,
            "next_offset": next_offset if has_more else None, "has_more": has_more,
            "detail_count": total, "details_returned": len(page),
            "count_kind": "job_deduplicated_technical_mentions_under_rules",
            "condition_counts_overlap": True, "condition_counts_are_verified_requirements": False,
            "warnings": metadata["warnings"] + ["技术提及不等于必备技能，也不证明直接用于RAG。条件分组可重叠，均为规则派生。"]}
