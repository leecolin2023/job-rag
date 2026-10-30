"""Evaluate one real user task using independently authored, source-backed labels.

The same question is tested across job-level counterexamples. Synthetic-spec labels
are never presented as human-reviewed real-world truth.
"""
from collections import Counter, defaultdict
import json
from pathlib import Path

from .task_runner import TASK_ID, aggregate, file_hash, load_dataset, read_jsonl, render_report, write_json


def load_gold(path, rows):
    by_id = {r["job_id"]: r for r in rows}
    labels = read_jsonl(path)
    seen = set()
    for label in labels:
        key = label.get("job_id")
        if key not in by_id or key in seen:
            raise ValueError("Gold references unknown or repeated job_id: " + str(key))
        seen.add(key)
        if label.get("label_source") not in {"synthetic_spec", "human_reviewed"}:
            raise ValueError(f"{key}: gold must declare label_source")
        if label.get("in_scope") not in (True, False, None):
            raise ValueError(f"{key}: in_scope must be true, false or null")
        if label["in_scope"] is None:
            if label.get("technologies"):
                raise ValueError(f"{key}: unresolved scope cannot have judged technologies")
            continue
        original = by_id[key]["description"]
        if label["in_scope"]:
            scope = label.get("scope_evidence")
            if not scope or scope.get("section") not in {"responsibilities", "requirements"}:
                raise ValueError(f"{key}: positive scope needs section and quote")
            if not scope.get("quote") or scope["quote"] not in original:
                raise ValueError(f"{key}: scope evidence is not in original JD")
        if label.get("tech_review_complete") and not label["in_scope"]:
            raise ValueError(f"{key}: excluded row cannot have technical judgments")
        for fact in label.get("technologies", []):
            if not label["in_scope"]:
                raise ValueError(f"{key}: excluded row cannot have technical facts")
            if not fact.get("technology") or not fact.get("quote") or fact["quote"] not in original:
                raise ValueError(f"{key}: technology evidence missing from source")
            if not fact.get("requirement_level"):
                raise ValueError(f"{key}: technology level must be explicit")
    return labels


def _section_contains(events, quote, expected, original):
    event = next((e for e in events if e["stage"] == "section"), None)
    if not event:
        return None
    for section in event.get("sections", []):
        if section["type"] == expected and quote in original[section["start"]:section["end"]]:
            return True
    return False


def _matching_facts(gold_fact, actual):
    """Match a claim to a technology AND original evidence; no keyword-only credit."""
    return [p for p in actual
            if p.get("technology") == gold_fact["technology"]
            and gold_fact["quote"] in p.get("quote", "")]


def _evidence_seen(events, fact, original):
    event = next((e for e in events if e["stage"] == "evidence"), None)
    if not event:
        return None
    return any(m.get("technology") == fact["technology"]
               and fact["quote"] in original[m["start"]:m["end"]]
               for m in event.get("mentions", []) if 0 <= m.get("start", -1) <= m.get("end", -1) <= len(original))


def _metric(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else None


def diagnose(dataset, predictions, trace, gold):
    """Score fully labeled comparisons, record first demonstrable failure.

    Failure attribution uses observable trace. Without an intermediate trace it is
    undetermined, never guessed to be retrieval, evidence or interpretation.
    """
    original = {r["job_id"]: r["description"] for r in dataset}
    pred = {p["job_id"]: p for p in predictions}
    if len(pred) != len(predictions):
        raise ValueError("Duplicate prediction job_id")
    if set(pred) != set(original):
        raise ValueError("Predictions must contain exactly one row per source job")
    trace_by_job = defaultdict(list)
    for item in trace:
        if item.get("job_id") in original:
            trace_by_job[item["job_id"]].append(item)
    failures, counts = [], Counter()
    category_expected, category_predicted = defaultdict(set), defaultdict(set)
    unknown = []
    for label in gold:
        job_id = label["job_id"]
        if label["in_scope"] is None:
            unknown.append(job_id)
            continue
        counts["scoped_rows"] += 1
        prediction = pred[job_id]
        events = trace_by_job[job_id]
        expected_scope = label["in_scope"]
        actual_scope = bool(prediction.get("in_scope"))
        if expected_scope:
            counts["scope_positives"] += 1
            if actual_scope:
                counts["scope_true_positive"] += 1
            else:
                evidence = label["scope_evidence"]
                recognized = _section_contains(events, evidence["quote"], evidence["section"], original[job_id])
                stage = "section" if recognized is False else ("selection" if recognized is True else "undetermined")
                failures.append({"job_id": job_id, "stage": stage, "kind": "scope_false_negative",
                                 "evidence": evidence["quote"]})
        elif actual_scope:
            failures.append({"job_id": job_id, "stage": "selection", "kind": "scope_false_positive"})
        if actual_scope:
            counts["scope_predicted_positive"] += 1
        if not expected_scope or not label.get("tech_review_complete"):
            continue
        counts["complete_tech_labeled_jobs"] += 1
        actual_facts = prediction.get("technologies", []) if actual_scope else []
        for expected in label.get("technologies", []):
            counts["technical_gold_facts"] += 1
            category_expected[expected["technology"]].add(job_id)
            possible = _matching_facts(expected, actual_facts)
            if not possible:
                if not actual_scope:
                    # The missing fact is a downstream symptom of the recorded scope failure.
                    continue
                presence = _evidence_seen(events, expected, original[job_id])
                stage = "interpretation" if presence is True else ("evidence" if presence is False else "undetermined")
                failures.append({"job_id": job_id, "stage": stage, "kind": "technical_fact_missing",
                                 "technology": expected["technology"], "evidence": expected["quote"]})
                continue
            counts["technical_facts_matched"] += 1
            expected_level = expected["requirement_level"]
            expected_alt = bool(expected.get("alternative", False))
            exact = any(p.get("requirement_level") == expected_level
                        and bool(p.get("alternative", False)) == expected_alt for p in possible)
            counts["conditions_compared"] += 1
            counts["conditions_correct"] += int(exact)
            if not exact:
                failures.append({"job_id": job_id, "stage": "interpretation", "kind": "condition_wrong",
                                 "technology": expected["technology"], "evidence": expected["quote"],
                                 "expected": {"requirement_level": expected_level, "alternative": expected_alt},
                                 "actual": [{"requirement_level": p.get("requirement_level"),
                                             "alternative": p.get("alternative")} for p in possible]})
        for item in actual_facts:
            if not 0 <= item.get("start", -1) <= item.get("end", -1) <= len(original[job_id]) \
                    or original[job_id][item["start"]:item["end"]] != item.get("quote"):
                failures.append({"job_id": job_id, "stage": "evidence", "kind": "invalid_source_span",
                                 "technology": item.get("technology")})
                continue
            category_predicted[item["technology"]].add(job_id)
            if not any(_matching_facts(g, [item]) for g in label.get("technologies", [])):
                failures.append({"job_id": job_id, "stage": "interpretation", "kind": "unsupported_extra_fact",
                                 "technology": item["technology"], "evidence": item.get("quote")})
    # Compare the observable aggregates against recomputed predictions, not against
    # incomplete real-world labels. Complete-fixture gold gets a separate gold comparison.
    summary = {
        "labeled_jobs": counts["scoped_rows"], "pending_scope_jobs": unknown,
        "scope_precision_on_labeled": _metric(counts["scope_true_positive"], counts["scope_predicted_positive"]),
        "scope_recall_on_labeled": _metric(counts["scope_true_positive"], counts["scope_positives"]),
        "technical_evidence_recall_on_complete_labeled": _metric(counts["technical_facts_matched"],
                                                                    counts["technical_gold_facts"]),
        "condition_accuracy_on_matched": _metric(counts["conditions_correct"], counts["conditions_compared"]),
        "complete_tech_labeled_jobs": counts["complete_tech_labeled_jobs"],
        "tech_count_error_on_complete_labeled": {
            key: {"gold_jobs": len(category_expected[key]), "predicted_jobs": len(category_predicted[key]),
                  "absolute_error": abs(len(category_expected[key]) - len(category_predicted[key]))}
            for key in sorted(set(category_expected) | set(category_predicted))
        },
        "failure_counts_by_first_stage": dict(sorted(Counter(f["stage"] for f in failures).items())),
        "failures": failures,
        "evaluation_scope": "labeled_subset_only",
        "full_corpus_semantic_accuracy_established": False,
        "unknown_tech_relation_not_scored": True,
        "label_sources": dict(Counter(g["label_source"] for g in gold)),
    }
    return summary


def evaluate(run_dir, dataset_path, gold_path, predictions_path=None, trace_path=None):
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("task") != TASK_ID or file_hash(dataset_path) != manifest.get("dataset_sha256"):
        raise ValueError("Dataset snapshot or task does not match frozen run manifest")
    dataset = load_dataset(dataset_path)
    labels = load_gold(gold_path, dataset)
    predictions = read_jsonl(predictions_path or run_dir / "predictions.jsonl")
    # A separate prediction file must not inherit the baseline's stage trace:
    # otherwise failure attribution would falsely credit an unrelated pipeline.
    trace = read_jsonl(trace_path) if trace_path else (
        [] if predictions_path else read_jsonl(run_dir / "trace.jsonl"))
    result = diagnose(dataset, predictions, trace, labels)
    if predictions_path is None:
        recorded_summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        expected_summary = aggregate(predictions)
        if recorded_summary != expected_summary:
            result["failures"].append({"stage": "aggregation", "kind": "aggregate_disagrees_with_predictions"})
        recorded_report = (run_dir / "report.md").read_text(encoding="utf-8")
        if recorded_report != render_report(manifest, recorded_summary):
            result["failures"].append({"stage": "answer", "kind": "report_disagrees_with_aggregate"})
        result["failure_counts_by_first_stage"] = dict(sorted(
            Counter(f["stage"] for f in result["failures"]).items()))
    result["gold_sha256"] = file_hash(gold_path)
    result["predictions_external"] = predictions_path is not None
    (run_dir / "evaluation.md").write_text(render_evaluation(result), encoding="utf-8")
    write_json(run_dir / "evaluation.json", result)
    return result


def render_evaluation(result):
    lines = [
        "# RAG 技术要求任务评测",
        "",
        "所有指标只针对已标注样本；合成规格标签不代表真实招聘数据已通过人工核验。",
        "",
        f"- 已确定范围的标注岗位：{result['labeled_jobs']}",
        f"- 待复核范围的岗位：{len(result['pending_scope_jobs'])}",
        f"- 范围筛选 Precision（已标注）：{result['scope_precision_on_labeled']}",
        f"- 范围筛选 Recall（已标注）：{result['scope_recall_on_labeled']}",
        f"- 技术证据召回（完整标注岗位）：{result['technical_evidence_recall_on_complete_labeled']}",
        f"- 条件判断准确率（匹配到证据的事实）：{result['condition_accuracy_on_matched']}",
        "",
        "## 首次失败环节",
        "",
        "| 环节 | 失败事实数 |",
        "| --- | ---: |",
    ]
    for key, value in result["failure_counts_by_first_stage"].items():
        lines.append(f"| {key} | {value} |")
    lines += ["", "## 技术岗位数误差（只在完整技术标注子集上比较）", "",
              "| 技术 | 标准岗位数 | 预测岗位数 | 绝对误差 |",
              "| --- | ---: | ---: | ---: |"]
    for key, item in result["tech_count_error_on_complete_labeled"].items():
        lines.append(f"| {key} | {item['gold_jobs']} | {item['predicted_jobs']} | {item['absolute_error']} |")
    lines += ["", "详细的逐证据错误和原文请查看 evaluation.json 与 trace.jsonl。",
              "本报告未证明全库语义正确，也未评测与 RAG 的真实技术关联关系。", ""]
    return "\n".join(lines)
