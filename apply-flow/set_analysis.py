#!/usr/bin/env python3
"""把岗位分析结论写回 jobs.csv 的 analysis 字段。

只改目标行的 analysis，其他字段和行保持不变；不访问网络、不点击沟通。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JOBS = ROOT / "data" / "jobs.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description="写入岗位分析结论到 jobs.csv")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--analysis", default=None, help="分析结论文本")
    parser.add_argument("--analysis-file", type=Path, default=None, help="从文件读取分析结论")
    parser.add_argument("--jobs-csv", type=Path, default=DEFAULT_JOBS)
    args = parser.parse_args()

    job_id = args.job_id.strip()
    if args.analysis_file:
        analysis = args.analysis_file.read_text(encoding="utf-8")
    else:
        analysis = args.analysis or ""
    analysis = " ".join(analysis.split()).strip()
    if not analysis:
        raise SystemExit("analysis 不能为空")
    if len(analysis) > 500:
        raise SystemExit(f"analysis 过长（{len(analysis)} 字符），请控制在 500 字符以内")

    with args.jobs_csv.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    if "analysis" not in fields:
        raise SystemExit("jobs.csv 缺少 analysis 列")
    if "job_id" not in fields:
        raise SystemExit("jobs.csv 缺少 job_id 列")

    matches = [r for r in rows if (r.get("job_id") or "").strip() == job_id]
    if not matches:
        raise SystemExit(f"找不到 job_id：{job_id}")
    old = matches[0].get("analysis", "")
    for row in matches:
        row["analysis"] = analysis

    fd, tmp = tempfile.mkstemp(prefix="jobs.csv.", suffix=".tmp", dir=str(args.jobs_csv.parent))
    os.close(fd)
    try:
        with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        os.replace(tmp, args.jobs_csv)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    # 读回校验：行数、列数和目标字段
    with args.jobs_csv.open(encoding="utf-8-sig", newline="") as f:
        check = list(csv.DictReader(f))
    target = next(r for r in check if (r.get("job_id") or "").strip() == job_id)
    if target.get("analysis", "") != analysis:
        raise SystemExit("写入后校验失败")
    print(json.dumps({
        "job_id": job_id,
        "old_analysis": old,
        "new_analysis": analysis,
        "rows": len(check),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
