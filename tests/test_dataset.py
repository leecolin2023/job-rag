from pathlib import Path

from job_rag.preprocessing.importer import import_csv
from job_rag.preprocessing.validation import parse_csv
from job_rag.indexing.worker import run_index_tasks
from job_rag.retrieval.search import SearchRequest
from job_rag.retrieval.answer import answer


DATA = Path(__file__).resolve().parents[1] / "data" / "jobs.csv"


def test_real_dataset(db, settings):
    content = DATA.read_bytes()
    rows = parse_csv(content)
    assert len(rows) == 593
    assert sum(bool(row["description"].strip()) for row in rows) == 592
    assert import_csv(db, settings, content)["created"] == 593
    assert run_index_tasks(db, settings)["failed"] == 0
    result = answer(db, settings, SearchRequest(query="广州 RAG", min_salary=20000, skills=["Python", "RAG"]))
    assert result["results"]
    for job in result["results"]:
        assert job["normalized"]["city"] == "广州"
        assert job["normalized"]["salary_min"] >= 20000
        assert job["job_status"] == "unknown"
    assert import_csv(db, settings, content)["unchanged"] == 593
