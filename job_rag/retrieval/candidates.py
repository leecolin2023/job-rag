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
    rerank: bool = False


def candidates(db, settings, request):
    with db.session() as session:
        cities = {job.normalized["city"] for job in session.scalars(select(Job))}
    original = SearchRequest(**request.model_dump(exclude={"reformulations", "candidate_limit", "rerank"}))
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
                item["evidence_queries"] = {str(chunk_id): [query] for chunk_id in item.get("evidence_chunk_ids", [])}
                item["evidence_merge_truncated"] = False
            else:
                record = records[item["key"]]
                for i, chunk_id in enumerate(item.get("evidence_chunk_ids", [])):
                    provenance = record["evidence_queries"].setdefault(str(chunk_id), [])
                    if query not in provenance:
                        provenance.append(query)
                    if chunk_id in record.get("evidence_chunk_ids", []):
                        continue
                    # Up to two source chunks per query, across at most five queries.
                    if len(record["evidence_chunk_ids"]) >= 10:
                        record["evidence_merge_truncated"] = True
                        continue
                    record["evidence_chunk_ids"].append(chunk_id)
                    record["evidence"].append(item["evidence"][i])
                    record["evidence_details"].append(item["evidence_details"][i])
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
    rerank_metadata = {"requested": False, "applied": False}
    if request.rerank:
        from .rerank import rerank_candidates
        output, rerank_metadata = rerank_candidates(db, settings, request.query, output)
        if not rerank_metadata["applied"]:
            warnings.add("模型重排未执行，保留召回融合顺序；原因见rerank字段。")
    return {"results": output[:request.candidate_limit], "total_candidates": len(output), "rerank": rerank_metadata,
            "count_kind": "bounded_recall_union_not_corpus_count",
            "count_complete": False, "returned_candidates": min(len(output), request.candidate_limit),
            "recall_limits": {"per_query_jobs": 30, "per_channel_chunks": 100,
                              "final_jobs": request.candidate_limit},
            "mode": "multi_query_hybrid" if settings.semantic_enabled else "multi_query_keyword",
            "semantic_assessment": "caller_llm_required", "queries": queries,
            "filters": base.model_dump(exclude={"query", "generate", "limit"}),
            "warnings": sorted(warnings)}
