"""Inspect frozen structured chunks without API calls or database changes."""
import argparse
from collections import Counter
import json
from pathlib import Path

from job_rag.chunking import parse_sections
from experiments.runner import load_prepared, read_lines, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("prepared")
    args = parser.parse_args()
    directory = Path(args.prepared)
    manifest, records, _ = load_prepared(directory)
    docs = read_lines(directory / manifest["arms"]["D_section_typed_1100"]["file"])
    by_id = {}
    for doc in docs:
        by_id.setdefault(doc["job_id"], []).append(doc)
    missing, unknown, samples = [], [], []
    for record in records:
        row = record["raw"]
        source = row["description"]
        covered = [False] * len(source)
        for section in parse_sections(source):
            if section.heading_start is not None:
                covered[section.heading_start:section.heading_end] = [True] * (section.heading_end - section.heading_start)
        own = by_id.get(row["job_id"], [])
        for doc in own:
            details = doc["details"]
            assert details["raw_text"] == source[details["source_start"]:details["source_end"]]
            covered[details["source_start"]:details["source_end"]] = [True] * (details["source_end"] - details["source_start"])
        lost = sum(not flag and not char.isspace() for flag, char in zip(covered, source))
        if lost:
            missing.append({"job_id": row["job_id"], "characters": lost})
        if own and all(doc["details"]["section_type"] == "unknown" for doc in own):
            unknown.append(row["job_id"])
        if len(samples) < 8 and any(doc["details"]["requirement_level"] in {"preferred", "mixed", "not_required"} for doc in own):
            samples.append({"job_id": row["job_id"], "title": row["title"], "chunks": own})
    summary = {"jobs": len(records), "chunks": len(docs), "fully_unknown_jobs": len(unknown), "unknown_job_ids": unknown,
               "missing_nonwhitespace_source": missing,
               "section_counts": dict(Counter(doc["details"]["section_type"] for doc in docs)),
               "condition_counts": dict(Counter(doc["details"]["requirement_level"] for doc in docs)),
               "note": "Coverage is a source-integrity check, NOT evidence that semantic labels are correct"}
    write_json(directory / "chunking-audit.json", summary)
    write_json(directory / "chunking-samples.json", samples)
    print(json.dumps({key: value for key, value in summary.items() if key != "unknown_job_ids"}, ensure_ascii=False, indent=2))
    if missing:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
