from dataclasses import replace

import pytest
from sqlalchemy import func, select

from job_rag.storage import Chunk, IndexTask, Job, Revision, StatusEvent
from job_rag.storage.serialization import serialize
from job_rag.preprocessing.importer import import_csv
from job_rag.preprocessing.validation import parse_csv
from job_rag.preprocessing.normalize import (
    COLLECTION_FIELDS, CONTENT_FIELDS, REQUIRED_COLUMNS, content_hash, digest, normalize)
from job_rag.indexing.worker import reindex, run_index_tasks
from job_rag.storage.status import set_status
from job_rag.retrieval.search import SearchRequest
from job_rag.retrieval.answer import answer

from conftest import csv_bytes, legacy_row, row


def test_bom_multiline_roundtrip():
    record = row(description='第一行，"带引号"\n第二行')
    assert parse_csv(csv_bytes(record)) == [record]


def test_content_and_collection_fields_partition_the_csv_contract():
    assert set(CONTENT_FIELDS) | set(COLLECTION_FIELDS) == (REQUIRED_COLUMNS | {"keywords"}) - {"job_id"}
    assert not set(CONTENT_FIELDS) & set(COLLECTION_FIELDS)
    assert "address" not in CONTENT_FIELDS


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

    monkeypatch.setattr("job_rag.indexing.worker.embed", fail)
    assert run_index_tasks(db, configured)["failed"] == 1
    with db.session() as session:
        task = session.scalar(select(IndexTask))
        assert task.error == "RuntimeError"
        assert session.get(Job, "boss:one").indexed_version is None
    monkeypatch.setattr("job_rag.indexing.worker.embed", lambda _, texts: [[1., 0.] for _ in texts])
    assert run_index_tasks(db, configured)["indexed"] == 1


def test_metadata_change_does_not_bump_version_or_reembed(db, settings, monkeypatch):
    configured = replace(settings, embedding_model="mock", embedding_api_key="dummy", embedding_dimensions=2)
    calls = []

    def vectors(_, texts):
        calls.append(texts)
        return [[1., 0.] for _ in texts]

    monkeypatch.setattr("job_rag.indexing.worker.embed", vectors)
    import_csv(db, configured, csv_bytes(row()))
    assert run_index_tasks(db, configured)["indexed"] == 1
    result = import_csv(db, configured, csv_bytes(row(collected_at="2026-10-24")))
    assert result["refreshed"] == 1 and result["updated"] == 0
    assert run_index_tasks(db, configured)["indexed"] == 0
    assert len(calls) == 1
    with db.session() as session:
        job = session.get(Job, "boss:one")
        assert job.version == 1
        assert job.raw["collected_at"] == "2026-10-24"
        assert session.scalar(select(func.count()).select_from(Revision)) == 1
        assert session.scalar(select(func.count()).select_from(IndexTask)) == 1


@pytest.mark.parametrize("changes", [
    {"collected_at": "2026-10-24"},
    {"status": "链接失效（未取得描述）"},
    {"keywords": "RAG；Agent"},
])
def test_collection_metadata_refresh_without_version_bump(db, settings, changes):
    import_csv(db, settings, csv_bytes(row()))
    result = import_csv(db, settings, csv_bytes(row(**changes)))
    assert result["refreshed"] == 1 and result["updated"] == 0
    with db.session() as session:
        job = session.get(Job, "boss:one")
        assert job.version == 1
        for field, value in changes.items():
            assert job.raw[field] == value
        assert session.scalar(select(func.count()).select_from(Revision)) == 1
        assert session.scalar(select(func.count()).select_from(IndexTask)) == 1
    if "status" in changes:
        with db.session() as session:
            assert serialize(session.get(Job, "boss:one"))["collection_status"] == changes["status"]


@pytest.mark.parametrize("changes", [
    {"title": "RAG 高级工程师"},
    {"salary": "30-50K·14薪"},
    {"url": "https://example.com/job/two"},
])
def test_content_change_still_bumps_version(db, settings, changes):
    import_csv(db, settings, csv_bytes(row()))
    result = import_csv(db, settings, csv_bytes(row(**changes)))
    assert result["updated"] == 1 and result["refreshed"] == 0
    with db.session() as session:
        job = session.get(Job, "boss:one")
        assert job.version == 2
        assert session.scalar(select(func.count()).select_from(Revision)) == 2
        assert session.scalar(select(func.count()).select_from(IndexTask)) == 2


OLD_CONTENT_FIELDS = ("title", "company", "location", "salary", "experience",
                      "education", "description", "address", "url")


def test_legacy_extra_columns_removed_without_version_bump(db, settings):
    legacy = legacy_row()
    assert import_csv(db, settings, csv_bytes(legacy))["created"] == 1
    # Simulate hashes written by the previous importer, whose content hash covered address.
    with db.session.begin() as session:
        job = session.get(Job, "boss:one")
        job.content_hash = digest({k: legacy.get(k, "") for k in OLD_CONTENT_FIELDS})
        job.raw_hash = digest(legacy)
    result = import_csv(db, settings, csv_bytes(row()))
    assert result["refreshed"] == 1 and result["updated"] == 0
    with db.session() as session:
        job = session.get(Job, "boss:one")
        assert job.version == 1
        assert job.raw == row()
        assert not {"address", "first_keyword", "keyword_count", "is_guangzhou"} & set(job.raw)
        assert job.content_hash == content_hash(row())
        assert job.raw_hash == digest(row())
        assert session.scalar(select(func.count()).select_from(Revision)) == 1
        assert session.scalar(select(func.count()).select_from(IndexTask)) == 1


def test_stale_stored_hashes_are_repaired_without_new_version(db, settings):
    import_csv(db, settings, csv_bytes(row()))
    with db.session.begin() as session:
        job = session.get(Job, "boss:one")
        job.raw_hash, job.content_hash = "stale", "stale"
    result = import_csv(db, settings, csv_bytes(row()))
    assert result["unchanged"] == 1 and result["updated"] == 0
    with db.session() as session:
        job = session.get(Job, "boss:one")
        assert job.version == 1
        assert job.raw_hash == digest(row())
        assert job.content_hash == content_hash(row())
        assert session.scalar(select(func.count()).select_from(Revision)) == 1
        assert session.scalar(select(func.count()).select_from(IndexTask)) == 1


def test_metadata_refresh_keeps_pending_task_valid(db, settings):
    import_csv(db, settings, csv_bytes(row()))
    assert import_csv(db, settings, csv_bytes(row(collected_at="2026-10-24")))["refreshed"] == 1
    assert run_index_tasks(db, settings) == {"indexed": 1, "failed": 0, "obsolete": 0}
    with db.session() as session:
        assert session.get(Job, "boss:one").version == 1


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
