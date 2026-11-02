#!/usr/bin/env python3
"""Read-only overview of the canonical job CSV, including manual annotations."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def summarize(path: Path) -> dict:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        if "job_id" not in fields:
            raise ValueError("Missing required job_id column")
        total = 0
        unique = set()
        statuses = Counter()
        descriptions = 0
        analyses = 0
        latest_collected_at = ""
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("CSV row has a malformed number of columns")
            total += 1
            job_id = row["job_id"].strip()
            if not job_id:
                raise ValueError("Empty job_id")
            unique.add(job_id)
            statuses[row.get("status", "")] += 1
            descriptions += bool(row.get("description", "").strip())
            analyses += bool(row.get("analysis", "").strip())
            latest_collected_at = max(latest_collected_at, row.get("collected_at", ""))
        return {
            "file": str(path),
            "columns": fields,
            "column_count": len(fields),
            "total_rows": total,
            "unique_job_ids": len(unique),
            "duplicate_job_ids": total - len(unique),
            "description_present": descriptions,
            "description_missing": total - descriptions,
            "analysis_present": analyses,
            "status_counts": dict(sorted(statuses.items())),
            "latest_collected_at": latest_collected_at,
        }


def main():
    parser = argparse.ArgumentParser(description="Report job CSV columns and coverage without modifying data")
    parser.add_argument("--csv", type=Path, default=ROOT / "data" / "jobs.csv")
    args = parser.parse_args()
    print(json.dumps(summarize(args.csv), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
