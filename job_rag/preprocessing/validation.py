"""Validate the whole external CSV before any database writes."""
import csv
import io

from .normalize import REQUIRED_COLUMNS


def parse_csv(content):
    if isinstance(content, bytes):
        content = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff"), newline=""))
    if not REQUIRED_COLUMNS.issubset(reader.fieldnames or []):
        raise ValueError("CSV missing columns: " + ", ".join(sorted(REQUIRED_COLUMNS - set(reader.fieldnames or []))))
    rows, seen = [], set()
    for line, row in enumerate(reader, 2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"CSV record {line}: column count mismatch")
        row = {k: v.strip() if k != "description" else v for k, v in row.items()}
        job_id = row["job_id"]
        if not job_id or job_id in seen:
            raise ValueError(f"CSV record {line}: empty or duplicate job_id")
        seen.add(job_id)
        rows.append(row)
    if not rows:
        raise ValueError("CSV has no records")
    return rows
