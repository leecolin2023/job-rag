from dataclasses import replace

import pytest
from sqlalchemy import func, select

from job_rag.db import Chunk, IndexTask, Job, Revision, StatusEvent
from job_rag.ingest import import_csv, parse_csv, reindex, run_index_tasks, set_status
from job_rag.normalize import normalize
from job_rag.search import SearchRequest, answer

from conftest import csv_bytes, row


def test_bom_multiline_roundtrip():
    record = row(description='第一行，"带引号"\n第二行')
    assert parse_csv(csv_bytes(record)) == [record]


@pytest.mark.parametrize("salary,period,minimum,maximum,months", [
    ("20-35K·14薪", "month", 20000, 35000, 14),
    ("300-500元/天", "day", 300, 500, None),
    ("50-80元/小时", "hour", 50, 80, None),
    ("面议", "unknown", None, None, None),
])
def test_salary(salary, period, minimum, maximum, months):
    norm = normalize(row(salary=salary))
    assert (norm["salary_period"], norm["salary_min"], norm["salary_max"], norm["salary_months"]) == (period, minimum, maximum, months)


def test_internship_and_unknown():
    norm = normalize(row(experience="5天/周；6个月", education="页面未显示"))
    assert norm["experience_min"] is None
    assert norm["employment_type"] == "internship"
    assert norm["education_level"] is None


def test_idempotent_import(db, settings):
    payload = csv_bytes(row())
    assert import_csv(db, settings, payload)["created"] == 1
    assert run_index_tasks(db, settings)["indexed"] == 1
    assert import_csv(db, settings, payload)["unchanged"] == 1
    assert run_index_tasks(db, settings)["indexed"] == 0
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(Revision)) == 1
        assert session.get(Job, "boss:one").job_status == "unknown"


def test_shorter_revision_cleans_old_chunks_and_blocks_stale(db, settings):
    import_csv(db, settings, csv_bytes(row(description="Python RAG\n" * 700)))
    run_index_tasks(db, settings)
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(Chunk)) > 1
    import_csv(db, settings, csv_bytes(row(description="Python RAG 新版本")))
    assert answer(db, settings, SearchRequest(query="RAG"))["results"] == []
    run_index_tasks(db, settings)
    result = answer(db, settings, SearchRequest(query="RAG"))
    assert len(result["results"]) == 1
    assert result["results"][0]["version"] == 2
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(Chunk)) == 1
        assert session.scalar(select(func.count()).select_from(Revision)) == 2


def test_missing_id_does_not_close_and_source_namespace(db, settings):
    import_csv(db, settings, csv_bytes(row(), row("two")))
    import_csv(db, settings, csv_bytes(row()))
    import_csv(db, settings, csv_bytes(row()), source="other")
    with db.session() as session:
        assert session.get(Job, "boss:two").job_status == "unknown"
        assert session.get(Job, "other:one") is not None


def test_reject_entire_bad_import(db, settings):
    with pytest.raises(ValueError):
        import_csv(db, settings, csv_bytes(row(), row()))
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0


def test_empty_description_is_auditable_but_not_searchable(db, settings):
    import_csv(db, settings, csv_bytes(row(description="", status="链接失效（未取得描述）")))
    run_index_tasks(db, settings)
    assert answer(db, settings, SearchRequest())["results"] == []
    with db.session() as session:
        assert session.get(Job, "boss:one").job_status == "unknown"


def test_failed_embedding_retries(db, settings, monkeypatch):
    configured = replace(settings, embedding_model="mock", embedding_api_key="dummy", embedding_dimensions=2)
    import_csv(db, configured, csv_bytes(row()))

    def fail(*_):
        raise RuntimeError("secret provider response")

    monkeypatch.setattr("job_rag.ingest.embed", fail)
    assert run_index_tasks(db, configured)["failed"] == 1
    with db.session() as session:
        task = session.scalar(select(IndexTask))
        assert task.error == "RuntimeError"
        assert session.get(Job, "boss:one").indexed_version is None
    monkeypatch.setattr("job_rag.ingest.embed", lambda _, texts: [[1., 0.] for _ in texts])
    assert run_index_tasks(db, configured)["indexed"] == 1


def test_metadata_update_reuses_vectors(db, settings, monkeypatch):
    configured = replace(settings, embedding_model="mock", embedding_api_key="dummy", embedding_dimensions=2)
    calls = []

    def vectors(_, texts):
        calls.append(texts)
        return [[1., 0.] for _ in texts]

    monkeypatch.setattr("job_rag.ingest.embed", vectors)
    import_csv(db, configured, csv_bytes(row()))
    run_index_tasks(db, configured)
    import_csv(db, configured, csv_bytes(row(collected_at="2026-10-24")))
    run_index_tasks(db, configured)
    assert len(calls) == 1
    with db.session() as session:
        assert session.get(Job, "boss:one").version == 2


def test_closed_status_excludes_without_reembedding(db, settings):
    import_csv(db, settings, csv_bytes(row()))
    run_index_tasks(db, settings)
    set_status(db, "boss:one", "active", "页面确认在招")
    assert len(answer(db, settings, SearchRequest(active_only=True))["results"]) == 1
    set_status(db, "boss:one", "closed", "页面显示停止招聘")
    assert answer(db, settings, SearchRequest())["results"] == []
    assert len(answer(db, settings, SearchRequest(include_closed=True))["results"]) == 1
    # Re-import never resurrects a closed job.
    import_csv(db, settings, csv_bytes(row(collected_at="2026-10-25")))
    run_index_tasks(db, settings)
    assert answer(db, settings, SearchRequest())["results"] == []
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(StatusEvent)) == 2


def test_old_task_obsoleted(db, settings):
    import_csv(db, settings, csv_bytes(row()))
    import_csv(db, settings, csv_bytes(row(description="新版本 RAG")))
    result = run_index_tasks(db, settings)
    assert result["obsolete"] == 1
    assert result["indexed"] == 1


def test_signature_change_blocks_old_index(db, settings):
    import_csv(db, settings, csv_bytes(row()))
    run_index_tasks(db, settings)
    changed = replace(settings, embedding_api_key="dummy", embedding_model="new-model")
    assert answer(db, changed, SearchRequest())["results"] == []
    assert reindex(db, settings)["indexed"] == 1
