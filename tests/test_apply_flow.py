"""Cross-workflow regression: application analysis must survive a new job crawl."""
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
NODE = os.environ.get("NODE") or "node"

MASTER_FIELDS = [
    "job_id", "title", "company", "location", "salary", "experience",
    "education", "url", "description", "status", "collected_at", "keywords", "analysis",
]
SOURCE_FIELDS = [
    "搜索关键词", "职位名称", "公司（卡片）", "工作区域", "薪资（页面展示）",
    "经验或实习要求", "学历要求", "职位详情链接",
    "岗位职责与任职要求原文", "职位ID", "采集日期",
]


def write_rows(path, fields, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_apply_analysis_survives_incremental_merge(tmp_path):
    master = tmp_path / "jobs.csv"
    write_rows(master, MASTER_FIELDS, [{
        "job_id": "old", "title": "Agent 工程师", "company": "某科技公司",
        "location": "广州", "salary": "20-30K", "experience": "3-5年",
        "education": "本科", "url": "https://example.org/old",
        "description": '初始职位要求：Python, RAG\\n"检索系统"',
        "status": "下线", "collected_at": "2026-10-31",
        "keywords": "RAG", "analysis": "",
    }])
    subprocess.run([
        PYTHON, str(ROOT / "apply-flow" / "set_analysis.py"),
        "--job-id", "old", "--jobs-csv", str(master),
        "--analysis", "公司在做什么：企业服务。岗位具体做什么：建设 RAG。",
    ], check=True, capture_output=True, text=True)

    snapshot = tmp_path / "new-batch.csv"
    def crawl(job_id):
        return {
            "搜索关键词": "AI", "职位名称": "Agent 工程师",
            "公司（卡片）": "某科技公司", "工作区域": "广州",
            "薪资（页面展示）": "20-30K",
            "经验或实习要求": "3-5年", "学历要求": "本科",
            "职位详情链接": f"https://example.org/{job_id}",
            "岗位职责与任职要求原文": "新版完整 JD" if job_id == "old" else "新岗位 JD",
            "职位ID": job_id, "采集日期": "2026-11-02",
        }
    write_rows(snapshot, SOURCE_FIELDS, [crawl("old"), crawl("new")])
    command = [
        PYTHON, str(ROOT / "data" / "data_merge" / "merge_jobs.py"),
        "--master", str(master), "--input", str(snapshot),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    with master.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2
    assert rows[0]["description"] == "新版完整 JD"
    assert rows[0]["status"] == "下线"
    assert rows[0]["analysis"] == "公司在做什么：企业服务。岗位具体做什么：建设 RAG。"
    assert rows[1]["status"] == "招聘中"
    assert rows[1]["analysis"] == ""

    first_output = master.read_bytes()
    subprocess.run(command, check=True, capture_output=True, text=True)
    assert master.read_bytes() == first_output


def run_apply_job(tmp_path, jobs_csv, contact_stdout, contact_exit=0):
    """Run apply_job.mjs against a stub contact script; no real browser involved."""
    contact = tmp_path / "fake-contact.mjs"
    contact.write_text(
        "console.log(JSON.stringify(" + contact_stdout + "));\n"
        + ("process.exitCode = %d;" % contact_exit),
        encoding="utf-8",
    )
    env = {**os.environ, "BROWSER_OPS_CONTACT": str(contact)}
    result = subprocess.run(
        [NODE, str(ROOT / "apply-flow" / "apply_job.mjs"),
         "--job-id", "test-job", "--jobs-csv", str(jobs_csv), "--confirm"],
        capture_output=True, text=True, env=env, check=False,
    )
    report = json.loads(result.stdout)["report"]
    rows = list(csv.DictReader(jobs_csv.open(encoding="utf-8-sig", newline="")))
    return report, rows, result


def test_apply_job_marks_status_after_successful_send(tmp_path):
    jobs_csv = tmp_path / "jobs.csv"
    write_rows(jobs_csv, [*MASTER_FIELDS], [{
        "job_id": "test-job", "title": "Agent 工程师", "company": "某科技公司",
        "location": "广州", "salary": "20-30K", "experience": "3-5年",
        "education": "本科", "url": "https://example.org/test-job",
        "description": "真实 JD",
        "status": "招聘中", "collected_at": "2026-11-02",
        "keywords": "RAG", "analysis": "公司在做什么：企业服务。岗位具体做什么：建设 RAG。",
    }])
    report, rows, _ = run_apply_job(tmp_path, jobs_csv,
        '{"clicked": true, "sent": true, "button_before": "立即沟通", "button_after": "继续沟通"}')
    assert report["error"] == ""
    assert report["status_updated"] is True
    assert report["status_before"] == "招聘中"
    assert report["status_after"] == "已投递"
    assert rows[0]["status"] == "已投递"
    assert rows[0]["analysis"] == "公司在做什么：企业服务。岗位具体做什么：建设 RAG。"


def test_apply_job_marks_status_when_already_contacted(tmp_path):
    jobs_csv = tmp_path / "jobs.csv"
    write_rows(jobs_csv, [*MASTER_FIELDS], [{
        "job_id": "test-job", "title": "Agent 工程师", "company": "某科技公司",
        "location": "广州", "salary": "20-30K", "experience": "3-5年",
        "education": "本科", "url": "https://example.org/test-job",
        "description": "真实 JD",
        "status": "招聘中", "collected_at": "2026-11-02",
        "keywords": "RAG", "analysis": "公司在做什么：企业服务。岗位具体做什么：建设 RAG。",
    }])
    report, rows, _ = run_apply_job(tmp_path, jobs_csv,
        '{"clicked": false, "sent": false, "error": "already_contacted", "button_before": "继续沟通"}')
    assert report["error"] == "already_contacted"
    assert report["status_updated"] is True
    assert report["status_after"] == "已投递"
    assert rows[0]["status"] == "已投递"


def test_apply_job_does_not_mark_status_on_failure(tmp_path):
    jobs_csv = tmp_path / "jobs.csv"
    write_rows(jobs_csv, [*MASTER_FIELDS], [{
        "job_id": "test-job", "title": "Agent 工程师", "company": "某科技公司",
        "location": "广州", "salary": "20-30K", "experience": "3-5年",
        "education": "本科", "url": "https://example.org/test-job",
        "description": "真实 JD",
        "status": "招聘中", "collected_at": "2026-11-02",
        "keywords": "RAG", "analysis": "公司在做什么：企业服务。岗位具体做什么：建设 RAG。",
    }])
    report, rows, result = run_apply_job(tmp_path, jobs_csv,
        '{"clicked": false, "sent": false, "error": "找不到按钮"}', contact_exit=1)
    assert report["error"] == "找不到按钮"
    assert report["status_updated"] is False
    assert rows[0]["status"] == "招聘中"


def test_apply_job_keeps_success_when_status_write_fails(tmp_path):
    jobs_csv = tmp_path / "jobs.csv"
    write_rows(jobs_csv, [*MASTER_FIELDS], [{
        "job_id": "test-job", "title": "Agent 工程师", "company": "某科技公司",
        "location": "广州", "salary": "20-30K", "experience": "3-5年",
        "education": "本科", "url": "https://example.org/test-job",
        "description": "真实 JD",
        "status": "招聘中", "collected_at": "2026-11-02",
        "keywords": "RAG", "analysis": "公司在做什么：企业服务。岗位具体做什么：建设 RAG。",
    }])
    contact_stdout = '{"clicked": true, "sent": true, "button_before": "立即沟通", "button_after": "继续沟通"}'
    contact = tmp_path / "fake-contact.mjs"
    contact.write_text("console.log(JSON.stringify(" + contact_stdout + "));", encoding="utf-8")
    env = {**os.environ,
           "BROWSER_OPS_CONTACT": str(contact),
           "PYTHON": str(tmp_path / "missing-python-binary")}
    result = subprocess.run(
        [NODE, str(ROOT / "apply-flow" / "apply_job.mjs"),
         "--job-id", "test-job", "--jobs-csv", str(jobs_csv), "--confirm"],
        capture_output=True, text=True, env=env, check=False,
    )
    report = json.loads(result.stdout)["report"]
    rows = list(csv.DictReader(jobs_csv.open(encoding="utf-8-sig", newline="")))
    assert result.returncode == 0
    assert report["error"] == ""
    assert report["sent"] is True
    assert report["status_updated"] is False
    assert report["status_error"]
    assert rows[0]["status"] == "招聘中"
