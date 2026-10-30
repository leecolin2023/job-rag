"""Multi-query evidence and opt-in full-JD rerank behavior."""
import json
from dataclasses import replace

import httpx
import pytest

from conftest import csv_bytes, row
from job_rag.preprocessing.importer import import_csv
from job_rag.indexing.worker import run_index_tasks
from job_rag.retrieval.candidates import CandidateRequest, candidates
from job_rag.storage.status import set_status


def test_multiple_queries_merge_distinct_evidence_with_provenance(db, settings, monkeypatch):
    import_csv(db, settings, csv_bytes(row()))
    from job_rag.querying.get_job import job_detail
    detail = job_detail(db, "one")
    def fake_answer(db, settings, request):
        ordinal = 1 if request.query == "RAG" else 2
        return {"warnings": [], "results": [{**detail, "evidence": [f"evidence {ordinal}"],
                "evidence_chunk_ids": [ordinal], "evidence_details": [{"section_type": "responsibilities"}]}]}
    monkeypatch.setattr("job_rag.retrieval.candidates.answer", fake_answer)
    result = candidates(db, settings, CandidateRequest(query="RAG", reformulations=["知识库", "RAG优化"]))
    record = result["results"][0]
    assert record["evidence_chunk_ids"] == [1, 2]
    assert record["evidence"] == ["evidence 1", "evidence 2"]
    assert record["evidence_queries"] == {"1": ["RAG"], "2": ["知识库", "RAG优化"]}


def test_rerank_is_explicit_and_preserves_full_jd(db, settings, monkeypatch):
    description = "岗位职责：RAG系统建设。\n任职要求：" + "Python后端开发，" * 130 + "尾部证据不得截断"
    import_csv(db, settings, csv_bytes(row("a", description=description), row("b", description="岗位职责：建设RAG。")))
    run_index_tasks(db, settings)
    configured = replace(settings, rerank_base_url="https://workspace.example/api/v1",
                         rerank_api_key="test-only-key", rerank_model="qwen3.7-text-rerank")
    original_client = httpx.Client
    calls = []
    def handle(request):
        payload = json.loads(request.content)
        calls.append(payload)
        return httpx.Response(200, json={"output": {"results": [
            {"index": 1, "relevance_score": .9}, {"index": 0, "relevance_score": .1}]}})
    monkeypatch.setattr("job_rag.providers.rerank.httpx.Client", lambda **kwargs:
                        original_client(**kwargs, transport=httpx.MockTransport(handle)))
    initial = candidates(db, configured, CandidateRequest(query="RAG"))
    assert not calls and not initial["rerank"]["applied"]
    result = candidates(db, configured, CandidateRequest(query="RAG", rerank=True))
    assert result["rerank"]["applied"]
    assert result["results"][0]["key"] == initial["results"][1]["key"]
    assert any(text.endswith(description) for text in calls[0]["input"]["documents"])
    assert all("[原文有截断" not in text for text in calls[0]["input"]["documents"])


def test_rerank_failure_and_post_model_status_change(db, settings, monkeypatch):
    import_csv(db, settings, csv_bytes(row()))
    run_index_tasks(db, settings)
    result = candidates(db, settings, CandidateRequest(query="RAG", rerank=True))
    assert result["rerank"]["reason"] == "not_configured"
    configured = replace(settings, rerank_base_url="https://example.com/api/v1", rerank_api_key="test", rerank_model="qwen3.7-text-rerank")
    def closes_job(*args):
        set_status(db, "boss:one", "closed", "模型返回前确认关闭")
        return [{"index": 0, "relevance_score": .9}], {}
    monkeypatch.setattr("job_rag.retrieval.rerank.rerank", closes_job)
    result = candidates(db, configured, CandidateRequest(query="RAG", rerank=True))
    assert result["results"] == [] and result["rerank"]["changed_jobs_excluded"] == 1


def test_invalid_provider_permutation_is_rejected(settings, monkeypatch):
    from job_rag.providers.rerank import rerank
    original_client = httpx.Client
    monkeypatch.setattr("job_rag.providers.rerank.httpx.Client", lambda **kwargs:
        original_client(**kwargs, transport=httpx.MockTransport(lambda request: httpx.Response(200,
            json={"output": {"results": [{"index": 0, "relevance_score": .9}]}}))))
    configured = replace(settings, rerank_base_url="https://example.com/api/v1", rerank_api_key="test", rerank_model="qwen3.7-text-rerank")
    with pytest.raises(ValueError, match="permutation"):
        rerank(configured, "RAG", ["a", "b"])
