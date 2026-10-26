"""Stage boundaries and canonical entry points after directory reorganization."""
import importlib
import ast
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select

from conftest import csv_bytes, row
from job_rag.chunking import build_documents
from job_rag.preprocessing.importer import import_csv
from job_rag.preprocessing.normalize import normalize
from job_rag.preprocessing.validation import parse_csv
from job_rag.storage import IndexTask, Job, Revision


def test_stage_specific_entry_points():
    storage = importlib.import_module("job_rag.storage")
    worker = importlib.import_module("job_rag.indexing.worker")
    assert storage.Job is Job
    assert storage.Database.__module__ == "job_rag.storage.database"
    assert import_csv.__module__ == "job_rag.preprocessing.importer"
    assert parse_csv.__module__ == "job_rag.preprocessing.validation"
    assert normalize.__module__ == "job_rag.preprocessing.normalize"
    assert worker.run_index_tasks.__module__ == "job_rag.indexing.worker"
    assert build_documents.__module__ == "job_rag.chunking.core"
    root = Path(__file__).resolve().parents[1] / "job_rag"
    for obsolete in ("normalize.py", "ingest.py", "db.py", "api.py", "mcp_server.py", "cli.py",
                     "search.py", "candidates.py", "catalog.py", "models.py", "chunking.py", "static"):
        assert not (root / obsolete).exists()


def test_shared_filters_and_serialization_have_single_definition():
    from job_rag.querying import catalog, filters
    from job_rag.retrieval import search
    from job_rag.storage.serialization import serialize

    assert catalog.StructuredFilters is search.StructuredFilters is filters.StructuredFilters
    assert catalog.matches is search.matches is filters.matches
    assert catalog.serialize is search.serialize is serialize


def test_querying_does_not_depend_on_retrieval_or_model_clients():
    root = Path(__file__).resolve().parents[1] / "job_rag" / "querying"
    for file in root.glob("*.py"):
        tree = ast.parse(file.read_text())
        for node in ast.walk(tree):
            modules = [node.module or ""] if isinstance(node, ast.ImportFrom) else (
                [alias.name for alias in node.names] if isinstance(node, ast.Import) else [])
            assert not any(set(module.split(".")) & {"retrieval", "providers", "interfaces"} for module in modules), file


def test_cli_serve_uses_new_asgi_entrypoint(monkeypatch):
    from job_rag.interfaces.cli import main

    called = []
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: called.append((args, kwargs)))
    monkeypatch.setattr(sys, "argv", ["job-rag", "serve", "--host", "127.0.0.1", "--port", "8765"])
    main()
    assert called == [(("job_rag.interfaces.api:app",), {"host": "127.0.0.1", "port": 8765})]


def test_queries_expose_details_and_stats_without_http(db, settings):
    from job_rag.querying.jobs import job_detail, knowledge_base_stats

    import_csv(db, settings, csv_bytes(row()))
    stats = knowledge_base_stats(db, settings)
    assert stats["total"] == 1 and stats["indexed"] == 0
    assert stats["statuses"] == {"unknown": 1}
    assert stats["cities"] == ["广州"]
    detail = job_detail(db, "one")
    assert detail["raw"]["description"] == row()["description"]
    assert len(detail["versions"]) == 1 and detail["status_history"] == []
    with pytest.raises(KeyError):
        job_detail(db, "missing")


def test_raw_preserved_and_no_index_execution(db, settings, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Preprocessing must not build chunks or call a model")

    monkeypatch.setattr("job_rag.indexing.worker.embed", forbidden)
    monkeypatch.setattr("job_rag.indexing.worker.build_documents", forbidden)
    original = row(description=' \n第一行，"原文"\r\n第二行\n ')
    result = import_csv(db, settings, csv_bytes(original))
    assert result["created"] == 1
    with db.session() as session:
        job = session.get(Job, "boss:one")
        assert job.raw == original
        assert job.indexed_version is None
        assert session.scalar(select(func.count()).select_from(IndexTask)) == 1


def test_mid_transaction_failure_rolls_back_all_tables(db, settings, monkeypatch):
    importer = importlib.import_module("job_rag.preprocessing.importer")

    def fail_second(record):
        if record["job_id"] == "second":
            raise RuntimeError("simulated normalization failure")
        return normalize(record)

    monkeypatch.setattr(importer, "normalize", fail_second)
    with pytest.raises(RuntimeError):
        import_csv(db, settings, csv_bytes(row(), row("second")))
    with db.session() as session:
        for model in (Job, Revision, IndexTask):
            assert session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize("payload", [b"job_id,description\none,test\n",
                                    csv_bytes(row(job_id=" ")),
                                    csv_bytes(row()) + b"second,too,few\n"])
def test_invalid_csv_never_partially_imported(db, settings, payload):
    with pytest.raises(ValueError):
        import_csv(db, settings, payload)
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0


def test_normalization_example_and_unknown_do_not_rewrite():
    original = row(location="广州·天河区", salary="20-35K·14薪", experience="3-5年")
    before = dict(original)
    norm = normalize(original)
    assert {key: norm[key] for key in ["city", "district", "salary_min", "salary_max", "salary_period",
                                      "salary_months", "experience_min", "experience_max", "education_level"]} == {
        "city": "广州", "district": "天河区", "salary_min": 20000, "salary_max": 35000,
        "salary_period": "month", "salary_months": 14, "experience_min": 3,
        "experience_max": 5, "education_level": "本科"}
    assert original == before
    unknown = normalize(row(salary="面议"))
    assert unknown["salary_min"] is None and "salary_not_comparable" in unknown["quality_flags"]
