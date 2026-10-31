"""Task-first RAG requirements experiments.

A zero-LLM, exhaustive literal baseline. Its outputs are predictions, NOT gold labels.
The module never touches a production DB/index or calls a paid model.
"""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from ..preprocessing.validation import parse_csv
from ..querying.conditions import evidence_item
from ..querying.sections import parse_query_sections, SECTION_RULE_VERSION
from ..querying.technical_vocabulary import TECHNOLOGIES, VOCABULARY_VERSION


TASK_ID = "rag-technical-requirements-v1"
ALLOWED = frozenset({"responsibilities", "requirements"})
RAG = re.compile(r"(?<![A-Za-z0-9_])RAG(?![A-Za-z0-9_])", re.I)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_jsonl(path, rows):
    Path(path).write_text("".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows), encoding="utf-8")


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_dataset(path):
    """Read immutable source CSV or small synthetic JSON fixtures."""
    path = Path(path)
    if path.suffix.lower() == ".csv":
        rows = parse_csv(path.read_bytes())
    elif path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("Fixture must be a JSON array")
        rows = data
    else:
        raise ValueError("Dataset must be .csv or .json")
    ids = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("job_id"), str) or not row["job_id"]:
            raise ValueError("Every record needs job_id")
        if row["job_id"] in ids:
            raise ValueError("Duplicate job_id: " + row["job_id"])
        if not isinstance(row.get("description"), str):
            raise ValueError("Every record needs a description string")
        ids.add(row["job_id"])
    if not rows:
        raise ValueError("Dataset must not be empty")
    return rows


def baseline_job(row):
    """Return a prediction and independently inspectable, source-aligned trace events."""
    job_id = row["job_id"]
    original = row["description"]
    events = [{
        "job_id": job_id, "stage": "source", "status": "ok" if original.strip() else "empty",
        "source_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
        "length": len(original),
    }]
    sections = parse_query_sections(original)
    unknown = sum(len(s["text"]) for s in sections if s["section_type"] == "unknown")
    events.append({
        "job_id": job_id, "stage": "section",
        "status": "needs_review" if unknown else "ok",
        "rule_version": SECTION_RULE_VERSION, "unknown_characters": unknown,
        "sections": [{"section_id": s["section_id"], "type": s["section_type"],
                      "start": s["source_start"], "end": s["source_end"]} for s in sections],
    })
    scope_hits = []
    for section in sections:
        if section["section_type"] not in ALLOWED:
            continue
        for match in RAG.finditer(section["text"]):
            left, right = section["source_start"] + match.start(), section["source_start"] + match.end()
            scope_hits.append({"section": section["section_type"], "quote": original[left:right],
                               "start": left, "end": right})
    included = bool(scope_hits)
    unknown_rag = any(RAG.search(s["text"]) for s in sections if s["section_type"] == "unknown")
    events.append({"job_id": job_id, "stage": "selection", "status": "ok",
                   "included": included, "scope_hits": scope_hits,
                   "unresolved_unknown_hit": unknown_rag and not included})
    mentions = []
    if included:
        for section in sections:
            if section["section_type"] not in ALLOWED:
                continue
            for category, (label, pattern) in TECHNOLOGIES.items():
                for match in re.finditer(pattern, section["text"], re.I):
                    left = section["source_start"] + match.start()
                    right = section["source_start"] + match.end()
                    evidence = evidence_item(original, section, left, right)
                    mention = {
                        "technology": category, "label": label, "section": section["section_type"],
                        "quote": evidence["text"], "start": evidence["source_start"],
                        "end": evidence["source_end"], "match_start": left, "match_end": right,
                        "matched_text": original[left:right],
                        "requirement_level": evidence["requirement_level"],
                        "alternative": evidence["alternative"],
                        "verified": False, "relation_to_rag": "unreviewed",
                    }
                    mentions.append(mention)
    events.append({"job_id": job_id, "stage": "evidence", "status": "ok",
                   "mentions": [{"technology": m["technology"], "start": m["start"],
                                 "end": m["end"], "match_start": m["match_start"],
                                 "match_end": m["match_end"]} for m in mentions]})
    events.append({"job_id": job_id, "stage": "interpretation", "status": "rule_derived_not_verified",
                   "facts": [{"technology": m["technology"],
                              "requirement_level": m["requirement_level"],
                              "start": m["start"], "end": m["end"]} for m in mentions]})
    prediction = {"job_id": job_id, "in_scope": included,
                  "scope_hits": scope_hits, "technologies": mentions,
                  "needs_scope_review": unknown_rag and not included,
                  "interpretation_method": "literal_rules_unverified"}
    return prediction, events


def aggregate(predictions):
    members = defaultdict(set)
    conditions = defaultdict(lambda: defaultdict(set))
    for p in predictions:
        if not p["in_scope"]:
            continue
        for item in p["technologies"]:
            members[item["technology"]].add(p["job_id"])
            conditions[item["technology"]][item["requirement_level"]].add(p["job_id"])
    categories = []
    for key, ids in members.items():
        categories.append({"technology": key, "label": TECHNOLOGIES.get(key, (key,))[0],
                           "job_count": len(ids),
                           "condition_job_counts": {level: len(jobs) for level, jobs in sorted(conditions[key].items())}})
    categories.sort(key=lambda item: (-item["job_count"], item["technology"]))
    return {"denominator_jobs": sum(p["in_scope"] for p in predictions),
            "unresolved_unknown_jobs": sum(p["needs_scope_review"] for p in predictions),
            "categories": categories, "semantic_assessment": "not_performed",
            "condition_counts_verified": False,
            "method": "versioned_literal_rules"}


def render_report(manifest, summary):
    lines = [
        "# RAG 岗位技术要求：字面基线（非语义核验）",
        "",
        "问题：统计岗位职责或者任职要求出现 RAG 的岗位中，相关的技术要求是什么？",
        "",
        f"- 数据集：{manifest['dataset']}；SHA256：{manifest['dataset_sha256']}",
        f"- 记录数：{manifest['corpus_jobs']}",
        f"- 职责/任职要求中独立 RAG 字面命中：{summary['denominator_jobs']} 岗位",
        f"- 未识别章节另有 RAG 命中、尚需人工复核：{summary['unresolved_unknown_jobs']} 岗位",
        "",
        "**以下是技术词在命中岗位中的共现统计，不是已核验的必备技能数量，也不证明技术直接用于 RAG。**",
        "",
        "| 技术类别 | 命中岗位数 |",
        "| --- | ---: |",
    ]
    for item in summary["categories"]:
        lines.append(f"| {item['label']} | {item['job_count']} |")
    lines += ["", "当前基线不调用大模型、不依赖 Top-K 检索；切分与检索阶段标记为不适用。",
              "正式技术要求、任选/否定和与 RAG 的直接关联，必须使用人工标注数据另行评测。",
              ""]
    return "\n".join(lines)


def run(dataset, output):
    """Produce a new immutable run directory; never overwrite prior output."""
    dataset, output = Path(dataset), Path(output)
    rows = load_dataset(dataset)
    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "task": TASK_ID, "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(dataset), "dataset_sha256": file_hash(dataset),
        "corpus_jobs": len(rows), "arm": "literal_full_scan_rules_v1",
        "scope_policy": "independent_RAG_in_responsibilities_or_requirements",
        "section_rule_version": SECTION_RULE_VERSION, "vocabulary_version": VOCABULARY_VERSION,
        "chunking": "not_applicable", "retrieval": "not_applicable",
        "gold_source": "none", "semantic_verification": False,
    }
    predictions, trace = [], []
    for row in rows:
        prediction, events = baseline_job(row)
        predictions.append(prediction)
        trace.extend(events)
    summary = aggregate(predictions)
    trace.append({"stage": "aggregation", "status": "ok",
                  "denominator_jobs": summary["denominator_jobs"],
                  "category_counts": {c["technology"]: c["job_count"] for c in summary["categories"]}})
    trace.append({"stage": "answer", "status": "template_from_aggregate", "semantic_verification": False})
    write_json(output / "manifest.json", manifest)
    write_jsonl(output / "predictions.jsonl", predictions)
    write_jsonl(output / "trace.jsonl", trace)
    write_json(output / "summary.json", summary)
    (output / "report.md").write_text(render_report(manifest, summary), encoding="utf-8")
    return {"run": str(output), "jobs": len(rows), "matched": summary["denominator_jobs"],
            "unresolved": summary["unresolved_unknown_jobs"], "verified": False}
