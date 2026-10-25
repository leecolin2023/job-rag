"""Integration check in an isolated, uniquely named PostgreSQL database.

Run inside the API container with /checks mounted read-only. Does not modify the
recruitment database; requires this development database user's CREATE DATABASE right.
"""
import csv
from dataclasses import replace
import io
import uuid

from sqlalchemy import text
from sqlalchemy.engine import make_url

from job_rag.config import Settings
from job_rag.db import Database
from job_rag.ingest import import_csv, run_index_tasks, set_status
from job_rag.search import SearchRequest, answer
import job_rag.ingest as ingest_module
import job_rag.search as search_module


settings = Settings()
name = "jobrag_check_" + uuid.uuid4().hex
control = Database(settings)
with control.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
    connection.execute(text(f'CREATE DATABASE "{name}"'))
test = None
try:
    url = make_url(settings.database_url).set(database=name).render_as_string(hide_password=False)
    configured = replace(settings, database_url=url, embedding_api_key="test-only", embedding_model="fake-2d", embedding_dimensions=2)
    test = Database(configured)
    test.initialize()
    ingest_module.embed = lambda _, texts: [[1., .2] for _ in texts]
    search_module.embed = lambda _, texts: [[1., .2] for _ in texts]
    row = dict(job_id="check", title="RAG应用工程师", company="测试", location="广州",
               salary="20-30K", experience="1-3年", education="本科", url="https://example.com",
               description="Python RAG 知识库开发", status="已获取描述", collected_at="2026-10-23")

    def payload():
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
        return stream.getvalue()

    assert import_csv(test, configured, payload())["created"] == 1
    assert run_index_tasks(test, configured)["indexed"] == 1
    result = answer(test, configured, SearchRequest(query="知识库 RAG", city="广州", min_salary=20000))
    assert result["mode"] == "hybrid", result["warnings"]
    assert result["results"][0]["job_id"] == "check"
    row["description"] = "新版 Python RAG"
    assert import_csv(test, configured, payload())["updated"] == 1
    assert answer(test, configured, SearchRequest(query="RAG"))["results"] == []
    assert run_index_tasks(test, configured)["indexed"] == 1
    assert answer(test, configured, SearchRequest(query="RAG"))["results"][0]["version"] == 2
    set_status(test, "boss:check", "closed", "集成测试")
    assert answer(test, configured, SearchRequest(query="RAG"))["results"] == []
    print("PASS: PostgreSQL + pgvector insert/distance, version replacement, closed-job exclusion")
finally:
    if test:
        test.engine.dispose()
    with control.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        # Only the exact unique database created by this script is removed.
        connection.execute(text(f'DROP DATABASE "{name}"'))
    control.engine.dispose()
