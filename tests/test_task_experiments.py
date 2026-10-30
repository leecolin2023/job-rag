"""Task-first experiments: scope, evidence, attribution and data integrity."""
import json
from pathlib import Path

import pytest

from job_rag.experiments.task_runner import load_dataset, read_jsonl, run, write_jsonl
from job_rag.experiments.task_eval import evaluate, load_gold
from job_rag.experiments.task_review import prepare_review_queue


ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "experiments" / "rag-tech-requirements"
DATASET = FIX / "fixtures.json"
GOLD = FIX / "gold.jsonl"


def test_fixture_run_produces_trace_and_reports_without_paid_models(tmp_path):
    output = tmp_path / "trial"
    result = run(DATASET, output)
    assert result["jobs"] == 16
    assert result["verified"] is False
    pred = {p["job_id"]: p for p in read_jsonl(output / "predictions.jsonl")}
    assert not pred["fx02"]["in_scope"]  # RAG in company introduction
    assert not pred["fx03"]["in_scope"]  # GraphRAG is not an independent RAG token
    assert not pred["fx11"]["in_scope"]  # RAG in bonus-only section
    assert not pred["fx12"]["in_scope"]  # RAGFlow excluded by default
    assert pred["fx04"]["in_scope"]      # Negated RAG still literally occurs
    assert pred["fx09"]["needs_scope_review"]  # unknown is unresolved, not a negative
    assert pred["fx08"]["in_scope"]
    assert "Docker" in [t["matched_text"] for t in pred["fx08"]["technologies"]]
    assert not any(t["matched_text"] == "Milvus" for t in pred["fx01"]["technologies"])
    assert not any(t["matched_text"] == "Docker" for t in pred["fx10"]["technologies"])
    summary = json.loads((output / "summary.json").read_text())
    cats = {c["technology"]: c for c in summary["categories"]}
    assert summary["denominator_jobs"] == 11
    assert summary["unresolved_unknown_jobs"] == 1
    assert cats["vector_retrieval"]["job_count"] == 3
    assert cats["python"]["job_count"] == 7
    assert "不是已核验的必备技能" in (output / "report.md").read_text()
    events = read_jsonl(output / "trace.jsonl")
    assert {"source", "section", "selection", "evidence",
            "interpretation", "aggregation", "answer"} <= {e["stage"] for e in events}
    with pytest.raises(FileExistsError):
        run(DATASET, output)


def test_gold_comparison_exposes_vocab_and_condition_failures(tmp_path):
    output = tmp_path / "trial"
    run(DATASET, output)
    result = evaluate(output, DATASET, GOLD)
    assert result["label_sources"] == {"synthetic_spec": 16}
    assert result["labeled_jobs"] == 15
    assert result["pending_scope_jobs"] == ["fx09"]
    assert result["scope_precision_on_labeled"] == 1.0
    assert result["scope_recall_on_labeled"] == 1.0
    assert result["technical_evidence_recall_on_complete_labeled"] < 1.0
    assert result["condition_accuracy_on_matched"] < 1.0
    assert any(f["kind"] == "technical_fact_missing" and f["technology"] == "java"
               and f["stage"] == "evidence" for f in result["failures"])
    assert any(f["stage"] == "interpretation" and f["kind"] == "condition_wrong"
               for f in result["failures"])
    assert not result["full_corpus_semantic_accuracy_established"]
    assert (output / "evaluation.md").exists()


def test_prediction_evidence_remains_reversible_to_source(tmp_path):
    output = tmp_path / "trial"
    run(DATASET, output)
    source = {r["job_id"]: r["description"] for r in load_dataset(DATASET)}
    for p in read_jsonl(output / "predictions.jsonl"):
        text = source[p["job_id"]]
        for fact in p["technologies"]:
            assert text[fact["start"]:fact["end"]] == fact["quote"]
            assert text[fact["match_start"]:fact["match_end"]] == fact["matched_text"]


def test_frozen_snapshot_and_gold_evidence_cannot_be_substituted(tmp_path):
    output = tmp_path / "trial"
    run(DATASET, output)
    changed = tmp_path / "changed.json"
    changed.write_text(DATASET.read_text().replace("Milvus", "FAISS"), encoding="utf-8")
    with pytest.raises(ValueError, match="snapshot"):
        evaluate(output, changed, GOLD)
    labels = read_jsonl(GOLD)
    labels[0]["scope_evidence"]["quote"] = "invented evidence"
    invalid = tmp_path / "invalid.jsonl"
    write_jsonl(invalid, labels)
    with pytest.raises(ValueError, match="scope evidence"):
        evaluate(output, DATASET, invalid)


def test_external_predictions_do_not_inherit_other_systems_stage_trace(tmp_path):
    output = tmp_path / "trial"
    run(DATASET, output)
    predictions = read_jsonl(output / "predictions.jsonl")
    target = next(p for p in predictions if p["job_id"] == "fx01")
    target["technologies"] = []
    external = tmp_path / "external.jsonl"
    write_jsonl(external, predictions)
    result = evaluate(output, DATASET, GOLD, predictions_path=external, output_dir=tmp_path / "external-scored")
    assert any(f["job_id"] == "fx01" and f["kind"] == "technical_fact_missing"
               and f["stage"] == "undetermined" for f in result["failures"])
    assert (tmp_path / "external-scored" / "evaluation_manifest.json").exists()


def test_aggregate_and_answer_drift_get_distinct_diagnostics(tmp_path):
    output = tmp_path / "trial"
    run(DATASET, output)
    summary_file = output / "summary.json"
    summary = json.loads(summary_file.read_text())
    summary["denominator_jobs"] += 1
    summary_file.write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
    result = evaluate(output, DATASET, GOLD)
    assert any(f["stage"] == "aggregation" for f in result["failures"])
    assert any(f["stage"] == "answer" for f in result["failures"])


def test_review_queue_is_stratified_and_cannot_be_used_as_gold(tmp_path):
    folder = tmp_path / "review"
    result = prepare_review_queue(DATASET, folder, limit=10)
    assert result["sampled"] == 10
    assert not result["gold_verified"]
    assert result["groups"]["unknown_section"] >= 1
    assert result["groups"]["alias_boundary"] >= 1
    assert result["groups"]["excluded_section"] >= 1
    queue = read_jsonl(folder / "review_queue.jsonl")
    assert len({row["job_id"] for row in queue}) == 10
    assert all(row["label_source"] == "pending_review" for row in queue)
    assert all(row["in_scope"] is None for row in queue)
    with pytest.raises(ValueError, match="label_source"):
        load_gold(folder / "review_queue.jsonl", load_dataset(DATASET))


def test_real_csv_exhaustive_baseline_runs_without_gold(tmp_path):
    output = tmp_path / "real"
    result = run(ROOT / "data" / "jobs.csv", output)
    assert result["jobs"] == 593
    assert result["matched"] > 0
    assert result["verified"] is False
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["retrieval"] == "not_applicable"
    assert manifest["semantic_verification"] is False
    assert len(read_jsonl(output / "predictions.jsonl")) == 593
    assert not (output / "evaluation.json").exists()
