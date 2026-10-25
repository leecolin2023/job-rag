import json

import httpx
import pytest

from job_rag.experiments.bailian import BailianClient, BailianConfig, BailianError


def config():
    return BailianConfig("https://workspace.cn-beijing.maas.aliyuncs.com", "fake-local-test-key", dimensions=256)


@pytest.mark.parametrize("index_field", ["index", "text_index"])
def test_native_embedding_batch_cache_and_query_type(tmp_path, index_field):
    requests = []

    def handle(request):
        payload = json.loads(request.content)
        requests.append(payload)
        return httpx.Response(200, json={"request_id": "test-id", "output": {"embeddings": [
            {index_field: index, "embedding": [1.] + [0.] * 255} for index, _ in enumerate(payload["input"]["texts"])]},
            "usage": {"total_tokens": 7}})

    client = BailianClient(config(), tmp_path / "cache.db", tmp_path / "journal.jsonl", transport=httpx.MockTransport(handle))
    try:
        vectors = client.embed(["重复文本"] * 3, "document")
        assert len(vectors) == 3
        assert len(requests) == 1
        assert requests[0]["input"]["texts"] == ["重复文本"]
        client.embed(["重复文本"], "document")
        assert len(requests) == 1
        client.embed(["重复文本"], "query")
        assert requests[-1]["parameters"]["text_type"] == "query"
        assert len(requests) == 2
        assert "fake-local-test-key" not in (tmp_path / "journal.jsonl").read_text()
        assert "api_key" not in client.config.public()
        assert "fake-local-test-key" not in repr(client.config)
    finally:
        client.close()


def test_rerank_full_candidate_permutation_and_cache(tmp_path):
    calls = []

    def handle(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"output": {"results": [{"index": 1, "relevance_score": .9}, {"index": 0, "relevance_score": .1}]}})

    client = BailianClient(config(), tmp_path / "cache.db", tmp_path / "journal.jsonl", transport=httpx.MockTransport(handle))
    try:
        assert client.rerank("query", ["a", "b"])[0]["index"] == 1
        assert client.rerank("query", ["a", "b"])[0]["index"] == 1
        assert len(calls) == 1
        client.rerank("query", ["a", "b"], "recruitment")
        assert len(calls) == 2
        assert calls[-1]["parameters"]["instruct"] == "recruitment"
    finally:
        client.close()


def test_auth_failure_no_retry_no_provider_secret_log(tmp_path):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(401, json={"message": "private provider body fake-local-test-key"})

    client = BailianClient(config(), tmp_path / "cache.db", tmp_path / "journal.jsonl", transport=httpx.MockTransport(handle))
    try:
        with pytest.raises(BailianError, match="HTTP 401") as captured:
            client.embed(["test"])
        assert len(calls) == 1
        assert "fake-local-test-key" not in str(captured.value)
        assert "private provider body" not in (tmp_path / "journal.jsonl").read_text()
    finally:
        client.close()


def test_request_cap_blocks_billing(tmp_path):
    client = BailianClient(config(), tmp_path / "cache.db", tmp_path / "journal.jsonl", max_requests=0)
    try:
        with pytest.raises(BailianError, match="cap"):
            client.embed(["test"])
    finally:
        client.close()


def test_cost_guard_blocks_before_http(tmp_path):
    calls = []
    client = BailianClient(config(), tmp_path / "cache.db", tmp_path / "journal.jsonl", max_cost_cny=.0000001,
                          transport=httpx.MockTransport(lambda request: calls.append(request)))
    try:
        with pytest.raises(BailianError, match="Cost guard"):
            client.embed(["large test payload"])
        assert calls == []
    finally:
        client.close()


def test_bad_host_and_missing_key_rejected():
    with pytest.raises(ValueError):
        BailianConfig("not-a-url", "test")
    with pytest.raises(ValueError):
        BailianConfig("https://example.com/api/v1", "test")
    with pytest.raises(ValueError):
        BailianConfig("https://example.com", "")


def test_partial_rerank_response_is_not_silently_scored(tmp_path):
    client = BailianClient(config(), tmp_path / "cache.db", tmp_path / "journal.jsonl",
                          transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
                              "output": {"results": [{"index": 0, "relevance_score": .9}]}})))
    try:
        with pytest.raises(BailianError, match="partial"):
            client.rerank("query", ["a", "b"])
    finally:
        client.close()


def test_runtime_native_embedding_protocol(settings, monkeypatch):
    from dataclasses import replace
    from job_rag.models import embed
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"output": {"embeddings": [{"text_index": 0, "embedding": [1., .5]}]}}

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def post(self, url, **kwargs):
            calls.append((url, kwargs["json"]))
            return Response()

    monkeypatch.setattr(httpx, "Client", Client)
    configured = replace(settings, embedding_api_format="dashscope", embedding_api_key="test-only",
                         embedding_model="mock", embedding_dimensions=2, embedding_base_url="https://example.com/api/v1")
    assert embed(configured, ["question"], text_type="query") == [[1., .5]]
    assert calls[0][0].endswith("/api/v1/services/embeddings/text-embedding/text-embedding")
    assert calls[0][1]["parameters"]["text_type"] == "query"
