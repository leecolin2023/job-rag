import csv

from scripts.report_dataset import summarize


def test_summary_includes_application_columns_without_changing_data(tmp_path):
    file = tmp_path / "jobs.csv"
    with file.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["job_id", "description", "status", "collected_at", "analysis"])
        writer.writeheader()
        writer.writerow({"job_id": "a", "description": "完整 JD", "status": "招聘中", "collected_at": "2026-11-01", "analysis": "已分析"})
        writer.writerow({"job_id": "b", "description": "", "status": "下线", "collected_at": "2026-11-02", "analysis": ""})
    before = file.read_bytes()
    result = summarize(file)
    assert result["total_rows"] == result["unique_job_ids"] == 2
    assert result["description_present"] == result["analysis_present"] == 1
    assert result["status_counts"] == {"下线": 1, "招聘中": 1}
    assert result["column_count"] == 5
    assert result["latest_collected_at"] == "2026-11-02"
    assert file.read_bytes() == before
