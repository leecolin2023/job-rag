"""Merge dated BOSS collection CSV snapshots into data/jobs.csv."""

from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from collections import Counter
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1]
MASTER_COLUMNS = (
    "job_id", "title", "company", "location", "salary", "experience",
    "education", "url", "description", "status", "collected_at", "keywords",
)
SOURCE_COLUMNS = {
    "搜索关键词": "keywords", "职位名称": "title", "公司（卡片）": "company",
    "工作区域": "location", "薪资（页面展示）": "salary",
    "经验或实习要求": "experience", "学历要求": "education",
    "职位详情链接": "url", "岗位职责与任职要求原文": "description",
    "职位ID": "job_id", "采集日期": "collected_at",
}
MISSING = {"", "4", "页面未显示", "未知", "暂无", "null", "none", "nan"}


def read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"{path}: missing CSV columns: {sorted(required - set(reader.fieldnames or []))}")
        rows = list(reader)
    for idx, row in enumerate(rows, 2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"{path}:{idx}: malformed CSV row")
    return rows


def is_valid(value: str) -> bool:
    return value.strip().casefold() not in MISSING


def merge_keywords(previous: str, current: str) -> str:
    values = [v.strip() for s in (previous, current) for v in s.replace(";", "；").split("；")]
    return "；".join(dict.fromkeys(v for v in values if is_valid(v)))


def merge_location(previous: str, current: str) -> str:
    if not is_valid(current):
        return previous
    if previous.startswith(current + "·") or previous.startswith(current + "-"):
        return previous
    return current


def merge_company(previous: str, current: str) -> str:
    if not is_valid(current):
        return previous
    # A new anonymous company label must not overwrite a named publisher.
    if current.startswith("某") and is_valid(previous) and not previous.startswith("某"):
        return previous
    return current


def normalize(source: dict[str, str]) -> dict[str, str]:
    row = {
        target: source.get(origin, "") if target == "description"
        else source.get(origin, "").strip()
        for origin, target in SOURCE_COLUMNS.items()
    }
    if len(row["collected_at"]) < 10:
        raise ValueError("collection row is missing a collection date")
    row["collected_at"] = row["collected_at"][:10]
    row["status"] = "招聘中"  # Catalog marker; not a live-site availability check.
    row["keywords"] = merge_keywords("", row["keywords"])
    return row


def merge(master: list[dict[str, str]], sources: list[list[dict[str, str]]]):
    if len({row["job_id"] for row in master}) != len(master):
        raise ValueError("master contains duplicate job_id")
    by_id = {row["job_id"]: row for row in master}
    stats = Counter()
    for input_rows in sources:
        seen = set()
        for raw in input_rows:
            row = normalize(raw)
            job_id = row["job_id"]
            if not is_valid(job_id):
                raise ValueError("source row has empty job_id")
            if job_id in seen:
                raise ValueError(f"duplicate job_id within a snapshot: {job_id}")
            seen.add(job_id)
            stats["input_rows"] += 1
            if job_id not in by_id:
                by_id[job_id] = row
                master.append(row)
                stats["inserted"] += 1
                continue
            old = by_id[job_id]
            stats["matched"] += 1
            # Older observations may expand provenance but cannot regress JD fields.
            recent = row["collected_at"] >= old["collected_at"]
            old["keywords"] = merge_keywords(old["keywords"], row["keywords"])
            if recent:
                for key in ("title", "salary", "experience", "education", "url", "description"):
                    if is_valid(row[key]):
                        old[key] = row[key]
                old["company"] = merge_company(old["company"], row["company"])
                old["location"] = merge_location(old["location"], row["location"])
                old["collected_at"] = max(old["collected_at"], row["collected_at"])
            # Do not mark missing old jobs closed, or undo an audited closed status.
    return master, dict(stats)


def output_columns(rows: list[dict[str, str]]) -> list[str]:
    """Keep canonical import fields first, then preserve all application-owned columns.

    Analysis, manual status and later human annotations must survive repeated
    collection merges. New collection rows may omit these optional columns.
    """
    extras = dict.fromkeys(
        column
        for row in rows
        for column in row
        if column not in MASTER_COLUMNS
    )
    return [*MASTER_COLUMNS, *extras]


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8-sig", newline="", dir=path.parent,
        prefix=".jobs-merge-", delete=False,
    ) as file:
        temp = Path(file.name)
        writer = csv.DictWriter(file, fieldnames=output_columns(rows), lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge BOSS snapshots into data/jobs.csv")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--date", help="Collection folder, e.g. 2026-10-31")
    group.add_argument("--input", nargs="+", type=Path, help="Explicit collection CSV files")
    parser.add_argument("--master", type=Path, default=DATA_DIR / "jobs.csv")
    parser.add_argument("--output", type=Path, help="Write to a separate CSV file")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    paths = sorted((DATA_DIR / "collections" / args.date).glob("*.csv")) if args.date else args.input
    if not paths:
        parser.error("No matching collection CSV files")
    master = read_csv(args.master, set(MASTER_COLUMNS))
    if any(not is_valid(row["job_id"]) for row in master):
        raise ValueError("master contains empty job_id")
    snapshots = [read_csv(path, set(SOURCE_COLUMNS)) for path in paths]
    merged, stats = merge(master, snapshots)
    print(json.dumps({
        "files": [str(path) for path in paths], "total": len(merged), **stats,
    }, ensure_ascii=False, indent=2))
    if not args.dry_run:
        write_csv(args.output or args.master, merged)


if __name__ == "__main__":
    main()
