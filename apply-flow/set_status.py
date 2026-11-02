#!/usr/bin/env python3
"""把岗位投递状态写回 jobs.csv 的 status 字段。

与 set_analysis.py 相同的写法：只更新目标行，其他字段和行保持不变；不访问网络、不点击沟通。
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
    parser = argparse.ArgumentParser(description="写入岗位状态到 jobs.csv")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--jobs-csv", type=Path, default=DEFAULT_JOBS)
    args = parser.parse_args()

    job_id = args.job_id.strip()
    status = args.status.strip()
    if not status:
        raise SystemExit("status 不能为空")

    with args.jobs_csv.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    if "status" not in fields:
        raise SystemExit("jobs.csv 缺少 status 列")
    if "job_id" not in fields:
        raise SystemExit("jobs.csv 缺少 job_id 列")

    matches = [r for r in rows if (r.get("job_id") or "").strip() == job_id]
    if not matches:
        raise SystemExit(f"找不到 job_id：{job_id}")
    old_status = [r.get("status", "") for r in matches]
    for row in matches:
        row["status"] = status

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
    target = [r for r in check if (r.get("job_id") or "").strip() == job_id]
    if any(r.get("status", "") != status for r in target):
        raise SystemExit("写入后校验失败")
    print(json.dumps({
        "job_id": job_id,
        "old_status": old_status,
        "new_status": status,
        "rows": len(check),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
