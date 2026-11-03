"""Regression tests for collection merge."""

from pathlib import Path
import json
import tempfile
import unittest

from data.data_merge.merge_jobs import MASTER_COLUMNS, merge, output_columns, read_csv, write_csv


def source(job_id="id", date="2026-10-31", company="公司", city="广州",
           text="原文", keyword="ai应用开发", skills='["Python"]'):
    return {
        "职位ID": job_id, "采集日期": date, "公司（卡片）": company,
        "工作区域": city, "岗位职责与任职要求原文": text, "搜索关键词": keyword,
        "技能标签": skills,
        "职位名称": "开发岗", "薪资（页面展示）": "20K",
        "经验或实习要求": "3年", "学历要求": "本科",
        "职位详情链接": "https://www.zhipin.com/job_detail/id.html",
    }


def existing():
    return {
        "job_id": "id", "collected_at": "2026-10-23", "company": "有名公司",
        "location": "广州·天河区", "description": "旧的完整 JD",
        "keywords": "RAG", "skills": "", "status": "招聘中", "title": "开发岗",
        "salary": "20K", "experience": "3年", "education": "本科",
        "url": "https://example.org",
    }


class CollectionMergeTests(unittest.TestCase):
    def test_preserve_specific_fields_and_idempotence(self):
        item = source(company="某科技公司", text="新的完整 JD")
        rows, stats = merge([existing()], [[item]])
        self.assertEqual(stats, {"input_rows": 1, "matched": 1})
        self.assertEqual(rows[0]["company"], "有名公司")
        self.assertEqual(rows[0]["location"], "广州·天河区")
        self.assertEqual(rows[0]["keywords"], "RAG；ai应用开发")
        self.assertEqual(rows[0]["skills"], '["Python"]')
        self.assertEqual(rows[0]["description"], "新的完整 JD")
        expected = [dict(row) for row in rows]
        rows, _ = merge(rows, [[item]])
        self.assertEqual(rows, expected)
        self.assertEqual(len(rows), 1)

    def test_insert_and_protect_newer_fields(self):
        old = existing()
        old["collected_at"] = "2026-11-01"
        rows, stats = merge([old], [[
            source(date="2026-10-23", text="过期 JD"), source(job_id="id2"),
        ]])
        self.assertEqual(stats["inserted"], 1)
        self.assertEqual(rows[0]["description"], "旧的完整 JD")
        self.assertEqual(rows[0]["collected_at"], "2026-11-01")
        self.assertEqual(rows[1]["status"], "招聘中")

    def test_duplicate_ids_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate job_id"):
            merge([], [[source(), source()]])

    def test_skills_union_and_empty_scrape_does_not_remove(self):
        old = existing()
        old["skills"] = '["RAG"]'
        rows, _ = merge([old], [[source(skills='["Python", "RAG"]')]])
        self.assertEqual(json.loads(rows[0]["skills"]), ["RAG", "Python"])

        rows, _ = merge(rows, [[source(date="2026-11-02", skills="[]")]])
        self.assertEqual(json.loads(rows[0]["skills"]), ["RAG", "Python"])

    def test_missing_skills_column_is_optional(self):
        item = source()
        item.pop("技能标签")
        rows, _ = merge([], [[item]])
        self.assertEqual(rows[0]["skills"], "")

    def test_master_without_skills_column_is_upgraded(self):
        old = existing()
        old.pop("skills")
        rows, _ = merge([old], [[source(skills='["RAG"]')]])
        self.assertEqual(rows[0]["skills"], '["RAG"]')

    def test_skills_accept_legacy_semicolon_text(self):
        old = existing()
        old["skills"] = "RAG；Python"
        rows, _ = merge([old], [[source(skills='["Agent"]')]])
        self.assertEqual(json.loads(rows[0]["skills"]), ["RAG", "Python", "Agent"])

    def test_bom_and_multiline_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.csv"
            item = existing()
            item["description"] = '甲,乙\n"quoted"'
            write_csv(path, [item])
            self.assertEqual(read_csv(path, set(MASTER_COLUMNS)), [item])
            self.assertEqual(path.read_bytes()[:3], b"\xef\xbb\xbf")

    def test_merge_preserves_analysis_manual_status_and_future_columns(self):
        """An analyst's annotations must survive the scheduled CSV merge."""
        old = existing()
        old["status"] = "下线"  # Explicitly verified: never re-open from a crawl.
        old["analysis"] = "这家公司的岗位要求分析"
        old["application_note"] = "已人工沟通"
        fresh = source(date="2026-11-02", text="更新后的完整 JD")
        inserted = source(job_id="new-job", date="2026-11-02")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.csv"
            rows, stats = merge([old], [[fresh, inserted]])
            self.assertEqual(stats["inserted"], 1)
            self.assertEqual(output_columns(rows)[-2:], ["analysis", "application_note"])
            write_csv(path, rows)
            actual = read_csv(path, set(MASTER_COLUMNS))
            self.assertEqual(len(actual), 2)
            self.assertEqual(actual[0]["status"], "下线")
            self.assertEqual(actual[0]["analysis"], old["analysis"])
            self.assertEqual(actual[0]["application_note"], old["application_note"])
            self.assertEqual(actual[0]["description"], "更新后的完整 JD")
            self.assertEqual(actual[1]["analysis"], "")
            self.assertEqual(actual[1]["application_note"], "")
            self.assertEqual(actual[1]["status"], "招聘中")

            repeated, stats = merge(actual, [[fresh, inserted]])
            self.assertEqual(stats.get("inserted", 0), 0)
            write_csv(path, repeated)
            self.assertEqual(read_csv(path, set(MASTER_COLUMNS)), actual)

    def test_extra_columns_survive_round_trip_without_crawl_updates(self):
        old = existing()
        old["analysis"] = "已分析"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.csv"
            write_csv(path, [old])
            result = read_csv(path, set(MASTER_COLUMNS))
            self.assertEqual(result, [old])


if __name__ == "__main__":
    unittest.main()
