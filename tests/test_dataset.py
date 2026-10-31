from pathlib import Path

from sqlalchemy import select

from job_rag.storage import Job
from job_rag.preprocessing.importer import import_csv
from job_rag.preprocessing.validation import parse_csv
from job_rag.indexing.worker import run_index_tasks
from job_rag.retrieval.search import SearchRequest
from job_rag.retrieval.answer import answer


DATA = Path(__file__).resolve().parents[1] / "data" / "jobs.csv"


def test_real_dataset(db, settings):
    content = DATA.read_bytes()
    rows = parse_csv(content)
    total = len(rows)
    assert total > 0
    assert len({row["job_id"] for row in rows}) == total
    assert sum(bool(row["description"].strip()) for row in rows) > 0
    assert import_csv(db, settings, content)["created"] == total
    assert run_index_tasks(db, settings)["failed"] == 0
    result = answer(db, settings, SearchRequest(query="广州 RAG", min_salary=20000, skills=["Python", "RAG"]))
    assert result["results"]
    for job in result["results"]:
        assert job["normalized"]["city"] == "广州"
        assert job["normalized"]["salary_min"] >= 20000
        assert job["job_status"] == "unknown"
    assert import_csv(db, settings, content)["unchanged"] == total
    with db.session() as session:
        assert set(session.scalars(select(Job.version))) == {1}
