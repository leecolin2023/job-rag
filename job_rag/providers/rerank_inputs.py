"""Full-source rerank inputs and explicit, offline input admission checks.

Limits checked 2026-10-28 against:
https://help.aliyun.com/zh/model-studio/text-rerank-api
Bytes are NOT provider tokens. The fallback is deliberately conservative.
"""
import hashlib
import json
from pathlib import Path


LIMITS = {
    "qwen3.7-text-rerank": {"documents": 500, "query": 4000, "document": 30000, "request": 120000},
    "qwen3-rerank": {"documents": 500, "query": 4000, "document": 4000, "request": 120000},
}


def representation(row):
    """Preserve the exact JD, including whitespace and original section order."""
    return f"岗位：{row['title']}\n岗位描述原文：\n{row['description']}"


class InputCounter:
    def __init__(self, tokenizer_path=""):
        self.tokenizer = None
        self.metadata = {"method": "utf8_bytes_plus_64_per_text", "provider_tokens_verified": False}
        if tokenizer_path:
            from tokenizers import Tokenizer
            path = Path(tokenizer_path)
            self.tokenizer = Tokenizer.from_file(str(path))
            self.metadata = {"method": "user_supplied_tokenizer_plus_64_per_text",
                             "tokenizer_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                             "provider_tokens_verified": False}

    def count(self, text):
        # Reserve framing space; this is an admission estimate, not billed usage.
        return (len(self.tokenizer.encode(text, add_special_tokens=False).ids)
                if self.tokenizer is not None else len(text.encode("utf-8"))) + 64


def payload(query, documents, model, instruct=""):
    result = {"model": model, "input": {"query": query, "documents": documents},
              "parameters": {"top_n": len(documents)}}
    if instruct:
        result["parameters"]["instruct"] = instruct
    return result


def inspect_inputs(query, documents, model="qwen3.7-text-rerank", instruct="", counter=None):
    if model not in LIMITS:
        raise ValueError("Rerank model input limits have not been verified for this model")
    counter = counter or InputCounter()
    limits = LIMITS[model]
    query_size = counter.count(query)
    instruction_size = counter.count(instruct) if instruct else 0
    document_sizes = [counter.count(text) for text in documents]
    estimated = (query_size + instruction_size) * len(documents) + sum(document_sizes)
    issues = []
    if len(documents) > limits["documents"]:
        issues.append("document_count")
    if query_size > limits["query"]:
        issues.append("query_estimate")
    if any(size > limits["document"] for size in document_sizes):
        issues.append("document_estimate")
    if estimated > limits["request"]:
        issues.append("request_estimate")
    body = payload(query, documents, model, instruct)
    return {"document_count": len(documents), "document_utf8_bytes": sum(len(d.encode()) for d in documents),
            "max_document_utf8_bytes": max((len(d.encode()) for d in documents), default=0),
            "query_utf8_bytes": len(query.encode()),
            "provider_formula_utf8_bytes": len(query.encode()) * len(documents) + sum(len(d.encode()) for d in documents),
            "http_json_utf8_bytes": len(json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()),
            "estimated_input_units_with_reserve": estimated, "counter": counter.metadata,
            "limits_tokens": limits, "request_limit_is_provider_recommendation": model == "qwen3.7-text-rerank",
            "admitted": not issues, "issues": issues}


def require_admitted(stats):
    if not stats["admitted"]:
        raise ValueError("Full-JD rerank input preflight failed: " + ", ".join(stats["issues"]) +
                         ". No text was truncated. Estimates are not provider token counts; "
                         "supply a tokenizer verified for the hosted model or prepare a smaller candidate set.")
