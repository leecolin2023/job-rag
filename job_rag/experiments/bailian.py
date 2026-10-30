"""Bailian native API adapter with explicit query/document types and safe telemetry.

Official references (checked 2026-10-25):
https://help.aliyun.com/zh/model-studio/text-embedding-synchronous-api
https://help.aliyun.com/zh/model-studio/text-rerank-api
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import time
from urllib.parse import urlsplit

from dotenv import dotenv_values
import httpx

from .rerank_inputs import InputCounter, inspect_inputs, payload, require_admitted


@dataclass(frozen=True)
class BailianConfig:
    host: str
    api_key: str = field(repr=False)
    embedding_model: str = "qwen3.7-text-embedding-flash"
    dimensions: int = 1024
    rerank_model: str = "qwen3.7-text-rerank"
    batch_size: int = 20
    trust_env: bool = False
    rerank_tokenizer_path: str = ""

    def __post_init__(self):
        url = urlsplit(self.host)
        if (url.scheme != "https" or not url.hostname or url.username or url.password or
                url.path not in {"", "/"} or url.query or url.fragment or "YOUR_WORKSPACE" in self.host):
            raise ValueError("Set BAILIAN_API_HOST to the real HTTPS workspace host, without an API path")
        if not self.api_key.strip():
            raise ValueError("BAILIAN_API_KEY is missing; configure a fresh key in a local restricted env file")
        if self.dimensions not in {256, 512, 768, 1024} or not 1 <= self.batch_size <= 20:
            raise ValueError("Qwen3.7 Flash requires dimensions 256/512/768/1024 and batch size 1-20")

    @classmethod
    def load(cls, path):
        values = {**dotenv_values(path), **os.environ}
        return cls(host=values.get("BAILIAN_API_HOST", "").rstrip("/"), api_key=values.get("BAILIAN_API_KEY", ""),
                   embedding_model=values.get("BAILIAN_EMBEDDING_MODEL", "qwen3.7-text-embedding-flash"),
                   dimensions=int(values.get("BAILIAN_EMBEDDING_DIMENSIONS", "1024")),
                   rerank_model=values.get("BAILIAN_RERANK_MODEL", "qwen3.7-text-rerank"),
                   batch_size=int(values.get("BAILIAN_BATCH_SIZE", "20")),
                   trust_env=values.get("BAILIAN_TRUST_ENV", "false").lower() == "true",
                   rerank_tokenizer_path=values.get("BAILIAN_RERANK_TOKENIZER_PATH", ""))

    def public(self):
        return {key: value for key, value in asdict(self).items() if key != "api_key"}


class BailianError(RuntimeError):
    """Safe error, deliberately excluding provider response bodies and credentials."""


def key_for(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


# Beijing list prices checked against the official model-pricing page, 2026-10-25.
# Estimates do not inspect account credits/free quota and are NOT billing guarantees.
PRICES_CNY_PER_MILLION = {"qwen3.7-text-embedding-flash": .125, "qwen3.7-text-rerank": .5}


class BailianClient:
    def __init__(self, config, cache_path, journal_path, max_requests=1000, transport=None, max_cost_cny=None):
        os.umask(0o077)
        self.config, self.max_requests, self.requests = config, max_requests, 0
        self.last_from_cache = False
        self.max_cost_cny, self.estimated_spend_cny = max_cost_cny, 0.0
        if max_cost_cny is not None and max_cost_cny <= 0:
            raise ValueError("max_cost_cny must be positive")
        self.cache_path = str(Path(cache_path).resolve())
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        self.cache = sqlite3.connect(cache_path)
        self.cache.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.journal = Path(journal_path)
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        self.http = httpx.Client(timeout=90, trust_env=config.trust_env, transport=transport)

    def close(self):
        self.http.close()
        self.cache.close()

    def _get(self, key):
        row = self.cache.execute("SELECT value FROM cache WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def _put(self, key, value):
        self.cache.execute("INSERT OR REPLACE INTO cache VALUES (?,?)", (key, json.dumps(value)))
        self.cache.commit()

    def _post(self, path, payload):
        price = PRICES_CNY_PER_MILLION.get(payload["model"])
        if self.max_cost_cny is not None and price is None:
            raise BailianError("No verified list price for this model; cannot apply a cost guard")
        inputs = payload.get("input", {})
        documents = inputs.get("texts", inputs.get("documents", []))
        # UTF-8 proxy + per-input prefix allowance, deliberately above normal token
        # usage for this corpus; provider tokenizer/account billing remain authoritative.
        reserved_tokens = sum(len(value.encode()) + 64 for value in documents)
        if "query" in inputs:
            reserved_tokens += (len(inputs["query"].encode()) + len(payload.get("parameters", {}).get("instruct", "").encode()) + 64) * len(documents)
        reserved_cost = reserved_tokens * (price or 0) / 1_000_000
        for attempt in range(4):
            if self.requests >= self.max_requests:
                raise BailianError("Request cap reached; resume later from cache with an explicit higher cap")
            if self.max_cost_cny is not None and self.estimated_spend_cny + reserved_cost > self.max_cost_cny:
                raise BailianError(f"Cost guard reached (estimated spent CNY {self.estimated_spend_cny:.6f}); cached progress is preserved")
            self.requests += 1
            start = time.monotonic()
            event = {"operation": path.rsplit("/", 1)[-1], "model": payload["model"],
                     "payload_hash": key_for(payload), "attempt": attempt + 1,
                     "started_at": datetime.now(timezone.utc).isoformat()}
            inputs = payload.get("input", {})
            source_texts = inputs.get("texts", inputs.get("documents", []))
            event["input_hashes"] = [key_for(value) for value in source_texts]
            event["input_count"] = len(source_texts)
            if "query" in inputs:
                event["query_hash"] = key_for(inputs["query"])
            if "text_type" in payload.get("parameters", {}):
                event["text_type"] = payload["parameters"]["text_type"]
            retry = False
            try:
                response = self.http.post(self.config.host + "/api/v1" + path,
                                          headers={"Authorization": f"Bearer {self.config.api_key}"}, json=payload)
                event["status"] = response.status_code
                if response.status_code in {429, 500, 502, 503, 504}:
                    retry = True
                    raise BailianError(f"Bailian transient HTTP {response.status_code}")
                if response.status_code != 200:
                    raise BailianError(f"Bailian HTTP {response.status_code}; check workspace, key, model access and endpoint region")
                body = response.json()
                if body.get("code"):
                    raise BailianError("Bailian returned an application error; inspect the provider console")
                usage = {key: value for key, value in body.get("usage", {}).items()
                         if key in {"total_tokens", "prompt_tokens"} and isinstance(value, int)}
                cost = usage["total_tokens"] * (price or 0) / 1_000_000 if "total_tokens" in usage else reserved_cost
                self.estimated_spend_cny += cost
                event.update(request_id=body.get("request_id"), usage=usage, estimated_cost_cny=cost)
                return body
            except httpx.TransportError:
                retry = True
                event["error"] = "transport_error_billing_unknown"
                if attempt == 3:
                    raise BailianError("Bailian transport failed; no silent lexical fallback in experiments") from None
            except BailianError:
                if not retry or attempt == 3:
                    raise
            finally:
                if "estimated_cost_cny" not in event:
                    self.estimated_spend_cny += reserved_cost
                    event["reserved_cost_cny_billing_unknown"] = reserved_cost
                event["latency_ms"] = round((time.monotonic() - start) * 1000, 2)
                with self.journal.open("a") as stream:
                    stream.write(json.dumps(event) + "\n")
            time.sleep(min(2 ** attempt, 8))
        raise BailianError("Bailian retry limit reached")

    def embed(self, texts, text_type="document"):
        if text_type not in {"query", "document"}:
            raise ValueError("Invalid embedding text_type")
        keys = [key_for({"operation": "embedding-v1", "host": self.config.host,
                         "model": self.config.embedding_model, "dimensions": self.config.dimensions,
                         "text_type": text_type, "text": text}) for text in texts]
        output = [self._get(key) for key in keys]
        missing = list(dict.fromkeys(i for i, value in enumerate(output) if value is None))
        # Deduplicate identical texts before billing; cache keys include query/document type.
        unique = {}
        for i in missing:
            unique.setdefault(keys[i], i)
        missing = list(unique.values())
        for offset in range(0, len(missing), self.config.batch_size):
            indexes = missing[offset:offset + self.config.batch_size]
            body = self._post("/services/embeddings/text-embedding/text-embedding", {
                "model": self.config.embedding_model, "input": {"texts": [texts[i] for i in indexes]},
                "parameters": {"text_type": text_type, "dimension": self.config.dimensions}})
            data = body["output"]["embeddings"]
            # Qwen3.7 workspace gateway uses index; older DashScope uses text_index.
            for item in data:
                if "index" in item and "text_index" in item and item["index"] != item["text_index"]:
                    raise BailianError("Conflicting embedding response indexes")
                item["resolved_index"] = item.get("text_index", item.get("index"))
                if type(item["resolved_index"]) is not int:
                    raise BailianError("Missing/invalid embedding response index")
            data = sorted(data, key=lambda item: item["resolved_index"])
            if len(data) != len(indexes) or [item["resolved_index"] for item in data] != list(range(len(indexes))):
                raise BailianError("Embedding response indexes/count mismatch")
            for i, item in zip(indexes, data):
                vector = item["embedding"]
                if (len(vector) != self.config.dimensions or not any(vector) or
                        not all(isinstance(x, (int, float)) and math.isfinite(x) for x in vector)):
                    raise BailianError("Embedding dimension/numeric validation failed")
                self._put(keys[i], vector)
        return [self._get(key) for key in keys]

    def rerank(self, query, documents, instruct=""):
        if not documents:
            return []
        stats = inspect_inputs(query, documents, self.config.rerank_model, instruct,
                               InputCounter(self.config.rerank_tokenizer_path))
        require_admitted(stats)
        request_payload = payload(query, documents, self.config.rerank_model, instruct)
        key = key_for({"operation": "rerank-v1", "host": self.config.host, "payload": request_payload})
        cached = self._get(key)
        self.last_from_cache = cached is not None
        if cached is not None:
            return cached
        body = self._post("/services/rerank/text-rerank/text-rerank", request_payload)
        results = body["output"]["results"]
        if sorted(item["index"] for item in results) != list(range(len(documents))):
            raise BailianError("Rerank indexes/count mismatch; refusing partial candidate comparison")
        if not all(isinstance(item["relevance_score"], (int, float)) and math.isfinite(item["relevance_score"]) for item in results):
            raise BailianError("Rerank scores are invalid")
        results = sorted(results, key=lambda item: (-item["relevance_score"], item["index"]))
        self._put(key, results)
        return results
