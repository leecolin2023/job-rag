"""Prepare a *review queue*, never a fake gold file, from a frozen job dataset."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from .task_runner import RAG, baseline_job, file_hash, load_dataset, write_json, write_jsonl


GROUPS = ("included_literal", "unknown_section", "alias_boundary", "excluded_section", "other_negative")


def _group(row, prediction):
    text = row["description"]
    if prediction["in_scope"]:
        return "included_literal"
    if prediction["needs_scope_review"]:
        return "unknown_section"
    if any(word in text.lower() for word in ("graphrag", "ragflow")):
        return "alias_boundary"
    if RAG.search(text):
        return "excluded_section"
    return "other_negative"


def prepare_review_queue(dataset_path, output, limit=40):
    """Create reproducibly sampled jobs requiring independent human labels.

    A proposed match is merely a rule-derived suggestion. The review records
    deliberately cannot pass load_gold until the reviewer replaces pending_review.
    """
    if limit < 1:
        raise ValueError("limit must be positive")
    dataset_path, output = Path(dataset_path), Path(output)
    rows = load_dataset(dataset_path)
    corpus_sha = file_hash(dataset_path)
    groups = defaultdict(list)
    for row in rows:
        prediction, _ = baseline_job(row)
        group = _group(row, prediction)
        groups[group].append((row, prediction))
    for group in groups:
        groups[group].sort(key=lambda x: hashlib.sha256(
            (corpus_sha + ":" + x[0]["job_id"]).encode("utf-8")).hexdigest())
    selected = []
    # Round-robin for coverage; fill any remaining budget from populated groups.
    while len(selected) < limit:
        progressed = False
        for group in GROUPS:
            if len(selected) >= limit:
                break
            if groups[group]:
                row, prediction = groups[group].pop(0)
                selected.append({
                    "job_id": row["job_id"], "review_group": group,
                    "description": row["description"],
                    "description_sha256": hashlib.sha256(row["description"].encode("utf-8")).hexdigest(),
                    "label_source": "pending_review",
                    "in_scope": None,
                    "scope_evidence": None,
                    "tech_review_complete": False,
                    "technologies": [],
                    "rule_suggestion_not_gold": {
                        "in_scope": prediction["in_scope"],
                        "scope_hits": prediction["scope_hits"],
                        "technologies": prediction["technologies"],
                    },
                })
                progressed = True
        if not progressed:
            break
    output.mkdir(parents=True, exist_ok=False)
    write_jsonl(output / "review_queue.jsonl", selected)
    write_json(output / "review_manifest.json", {
        "dataset": str(dataset_path), "dataset_sha256": corpus_sha,
        "source_rows": len(rows), "sampled": len(selected),
        "groups": {g: sum(item["review_group"] == g for item in selected) for g in GROUPS},
        "review_status": "unreviewed",
        "instruction": "Read complete JD. Independently decide scope, annotate each technology and exact source quote. "
                       "Create a SEPARATE gold.jsonl; do not rename rule_suggestion_not_gold to gold.",
    })
    return {"review_queue": str(output / "review_queue.jsonl"), "sampled": len(selected),
            "groups": {g: sum(item["review_group"] == g for item in selected) for g in GROUPS},
            "gold_verified": False}
