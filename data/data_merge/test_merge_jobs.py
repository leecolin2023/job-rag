"""Regression tests for collection merge."""

from pathlib import Path
import tempfile
import unittest

from data.data_merge.merge_jobs import MASTER_COLUMNS, merge, read_csv, write_csv


def source(job_id="id", date="2026-10-31", company="公司", city="广州",
           text="原文", keyword="ai应用开发"):
    return {
        "职位ID": job_id, "采集日期": date, "公司（卡片）": company,
        "工作区域": city, "岗位职责与任职要求原文": text, "搜索关键词": keyword,
        "职位名称": "开发岗", "薪资（页面展示）": "20K",
        "经验或实习要求": "3年", "学历要求": "本科",
        "职位详情链接": "https://www.zhipin.com/job_detail/id.html",
    }


def existing():
    return {
        "job_id": "id", "collected_at": "2026-10-23", "company": "有名公司",
        "location": "广州·天河区", "description": "旧的完整 JD",
        "keywords": "RAG", "status": "招聘中", "title": "开发岗",
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

    def test_bom_and_multiline_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.csv"
            item = existing()
            item["description"] = '甲,乙\n"quoted"'
            write_csv(path, [item])
            self.assertEqual(read_csv(path, set(MASTER_COLUMNS)), [item])
            self.assertEqual(path.read_bytes()[:3], b"\xef\xbb\xbf")


if __name__ == "__main__":
    unittest.main()
