"""Bounded multi-query recall for harness-side LLM semantic assessment."""
from collections import Counter

from pydantic import Field
from sqlalchemy import select

from ..storage import Job
from .search import SearchRequest, resolve_filters
from .answer import answer


class CandidateRequest(SearchRequest):
    reformulations: list[str] = Field(default_factory=list, max_length=4)
    candidate_limit: int = Field(default=20, ge=1, le=60)


def candidates(db, settings, request):
    with db.session() as session:
        cities = {job.normalized["city"] for job in session.scalars(select(Job))}
    original = SearchRequest(**request.model_dump(exclude={"reformulations", "candidate_limit"}))
    base = resolve_filters(original, cities)
    queries = list(dict.fromkeys([request.query] + request.reformulations))
    if any(len(query) > 2000 for query in queries):
        raise ValueError("Each reformulation must be at most 2000 characters")
    scores, records, warnings = Counter(), {}, set()
    for query in queries:
        # Hard constraints come from the original request, not invented reformulations.
        filters = base.model_copy(update={"query": query, "limit": 30, "generate": False, "infer_filters": False})
        result = answer(db, settings, filters)
        warnings.update(result["warnings"])
        for rank, item in enumerate(result["results"]):
            scores[item["key"]] += 1 / (60 + rank + 1)
            if item["key"] not in records:
                records[item["key"]] = item
                item["matched_queries"] = []
            records[item["key"]]["matched_queries"].append(query)
    ordered = sorted(records, key=lambda key: (-scores[key], key))
    output = []
    # Recheck after all reformulations; a candidate may have changed between calls.
    with db.session() as session:
        for key in ordered:
            item, current = records[key], session.get(Job, key)
            if current is None or current.version != item["version"] or current.job_status != item["job_status"]:
                warnings.add("部分候选在召回期间变化，已排除，请重新检索。")
                continue
            item["fusion_score"] = round(scores[key], 6)
            output.append(item)
    return {"results": output[:request.candidate_limit], "total_candidates": len(output),
            "count_kind": "bounded_recall_union_not_corpus_count",
            "count_complete": False, "returned_candidates": min(len(output), request.candidate_limit),
            "recall_limits": {"per_query_jobs": 30, "per_channel_chunks": 100,
                              "final_jobs": request.candidate_limit},
            "mode": "multi_query_hybrid" if settings.semantic_enabled else "multi_query_keyword",
            "semantic_assessment": "caller_llm_required", "queries": queries,
            "filters": base.model_dump(exclude={"query", "generate", "limit"}),
            "warnings": sorted(warnings)}
