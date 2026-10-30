"""Optional native DashScope rerank; full inputs, no truncation or partial scores."""
import math
import httpx
from .rerank_inputs import InputCounter, inspect_inputs, payload, require_admitted


class RerankInputError(ValueError):
    """Full input cannot be admitted without truncation."""


def rerank(settings, query, documents):
    instruction = ("Rank recruitment jobs by the user's intent. Prefer concrete job responsibilities over company "
                   "introductions. Preserve negation, alternatives and mandatory versus preferred qualifications.")
    try:
        stats = inspect_inputs(query, documents, settings.rerank_model, instruction,
                               InputCounter(settings.rerank_tokenizer_path))
        require_admitted(stats)
    except (ValueError, OSError) as exc:
        raise RerankInputError("Full rerank input could not be admitted") from exc
    with httpx.Client(timeout=60, trust_env=False) as client:
        response = client.post(settings.rerank_base_url.rstrip("/") + "/services/rerank/text-rerank/text-rerank",
            headers={"Authorization": f"Bearer {settings.rerank_api_key}"},
            json=payload(query, documents, settings.rerank_model, instruction))
        response.raise_for_status()
        body = response.json()
    ranked = body["output"]["results"]
    if (any(type(item["index"]) is not int for item in ranked)
            or sorted(item["index"] for item in ranked) != list(range(len(documents)))
            or any(type(item["relevance_score"]) not in {int, float} or not math.isfinite(item["relevance_score"]) for item in ranked)):
        raise ValueError("Invalid rerank permutation or scores")
    return sorted(ranked, key=lambda item: (-item["relevance_score"], item["index"])), stats
