from dataclasses import replace

from fastapi.testclient import TestClient

from job_rag.api import create_app
from job_rag.ingest import import_csv, run_index_tasks, set_status
from job_rag.search import SearchRequest, answer

from conftest import csv_bytes, row


def seed(db, settings):
    import_csv(db, settings, csv_bytes(
        row(), row("low", salary="10-25K"),
        row("day", salary="300-500元/天"),
        row("senior", experience="5-10年"),
        row("other", location="深圳·南山区", description="Java 后端", title="后端工程师"),
    ))
    run_index_tasks(db, settings)


def test_hard_filters(db, settings):
    seed(db, settings)
    result = answer(db, settings, SearchRequest(query="广州 RAG", min_salary=20000, experience_years=3, skills=["Python", "RAG"]))
    assert [r["job_id"] for r in result["results"]] == ["one"]
    assert result["filters"]["city"] == "广州"
    assert "未确认" in "".join(result["warnings"])
    result = answer(db, settings, SearchRequest(city="广州", min_salary=20000, salary_mode="overlap", experience_years=3))
    assert {r["job_id"] for r in result["results"]} == {"one", "low"}


def test_unknown_never_claimed_active(db, settings):
    seed(db, settings)
    result = answer(db, settings, SearchRequest(query="RAG", generate=True))
    assert result["answer_mode"] == "extractive"
    assert "未核验" in result["answer"]
    assert answer(db, settings, SearchRequest(active_only=True))["results"] == []


def test_no_results_for_unrelated_english_query(db, settings):
    seed(db, settings)
    assert answer(db, settings, SearchRequest(query="zzzznonexistent"))["results"] == []


def test_suspected_expired_hidden_by_default(db, settings):
    import_csv(db, settings, csv_bytes(row()))
    run_index_tasks(db, settings)
    set_status(db, "boss:one", "suspected_expired", "多次访问失败，不能确认关闭")
    assert answer(db, settings, SearchRequest())["results"] == []
    assert len(answer(db, settings, SearchRequest(include_closed=True))["results"]) == 1


def test_hybrid_and_generation_fallback(db, settings, monkeypatch):
    configured = replace(settings, embedding_api_key="dummy", embedding_model="mock", embedding_dimensions=2,
                         chat_api_key="dummy", chat_model="mock")
    monkeypatch.setattr("job_rag.ingest.embed", lambda _, texts: [[1., 0.] for _ in texts])
    import_csv(db, configured, csv_bytes(row()))
    run_index_tasks(db, configured)
    monkeypatch.setattr("job_rag.search.embed", lambda _, texts, **kwargs: [[1., 0.] for _ in texts])
    monkeypatch.setattr("job_rag.search.chat", lambda *_: "匹配岗位 [1]")
    result = answer(db, configured, SearchRequest(query="语义测试", generate=True))
    assert result["mode"] == "hybrid"
    assert result["answer_mode"] == "llm"
    monkeypatch.setattr("job_rag.search.chat", lambda *_: "编造引用 [99]")
    assert answer(db, configured, SearchRequest(query="RAG", generate=True))["answer_mode"] == "extractive"


def test_state_rechecked_after_model_response(db, settings, monkeypatch):
    configured = replace(settings, chat_api_key="dummy", chat_model="mock")
    import_csv(db, configured, csv_bytes(row()))
    run_index_tasks(db, configured)

    def close_during_generation(*_):
        set_status(db, "boss:one", "closed", "生成期间关闭")
        return "候选岗位 [1]"

    monkeypatch.setattr("job_rag.search.chat", close_during_generation)
    result = answer(db, configured, SearchRequest(query="RAG", generate=True))
    assert result["results"] == []
    assert "重新查询" in result["answer"]


def test_api(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/health").json()["status"] == "ok"
        assert client.post("/api/import", content=csv_bytes(row())).status_code == 401
        headers = {"Authorization": "Bearer test-secret", "Content-Type": "text/csv"}
        assert client.post("/api/import", content=csv_bytes(row()), headers=headers).json()["created"] == 1
        run_index_tasks(app.state.db, settings)
        assert client.get("/api/stats").json()["total"] == 1
        assert client.post("/api/search", json={"query": "RAG"}).json()["results"][0]["job_id"] == "one"
        detail = client.get("/api/jobs/one").json()
        assert detail["raw"]["description"].startswith("岗位职责")
        assert len(detail["versions"]) == 1
        assert client.post("/api/jobs/one/status", json={"status": "closed", "reason": "确认关闭"}, headers={"Authorization": "Bearer test-secret"}).status_code == 200
        assert client.post("/api/search", json={"query": "RAG"}).json()["results"] == []
        assert client.post("/api/search", json={"limit": 100}).status_code == 422
        assert client.get("/api/jobs/nonexistent").status_code == 404


def test_admin_disabled_by_default(settings):
    with TestClient(create_app(replace(settings, admin_token=""))) as client:
        assert client.post("/api/import", content=csv_bytes(row())).status_code == 403
