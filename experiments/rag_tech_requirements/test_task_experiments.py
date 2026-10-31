"""Task-first experiments: scope, evidence, attribution and data integrity."""
import json
from pathlib import Path

import pytest

from experiments.rag_tech_requirements.task_runner import load_dataset, read_jsonl, run, write_jsonl
from experiments.rag_tech_requirements.task_eval import evaluate, load_gold
from experiments.rag_tech_requirements.task_review import prepare_review_queue


ROOT = Path(__file__).resolve().parents[2]
FIX = Path(__file__).resolve().parent
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
    bonus = next(t for t in pred["fx01"]["technologies"] if t["matched_text"] == "Milvus")
    assert bonus["section"] == "preferred"
    assert bonus["requirement_level"] == "preferred"
    assert not any(t["matched_text"] == "Docker" for t in pred["fx10"]["technologies"])
    assert pred["fx11"]["technologies"] == []  # A bonus-only RAG mention is not in scope
    summary = json.loads((output / "summary.json").read_text())
    cats = {c["technology"]: c for c in summary["categories"]}
    assert summary["denominator_jobs"] == 11
    assert summary["unresolved_unknown_jobs"] == 1
    assert cats["vector_retrieval"]["job_count"] == 4
    assert cats["vector_retrieval"]["condition_job_counts"]["preferred"] == 1
    assert cats["python"]["job_count"] == 7
    assert "不是已核验的必备技能" in (output / "report.md").read_text()
    report = (output / "report.md").read_text()
    assert "优先（规则）" in report
    assert "独立加分项技术也纳入优先统计" in report
    events = read_jsonl(output / "trace.jsonl")
    assert {"source", "section", "selection", "evidence",
            "interpretation", "aggregation", "answer"} <= {e["stage"] for e in events}
    with pytest.raises(FileExistsError):
        run(DATASET, output)



def test_bonus_section_only_adds_preferred_evidence_after_scope_matches():
    from experiments.rag_tech_requirements.task_runner import aggregate, baseline_job

    eligible = {
        "job_id": "eligible",
        "description": "岗位职责：建设 RAG 系统。\\n任职要求：必须掌握 Milvus。\\n加分项：熟悉 Milvus。",
    }
    bonus_only = {
        "job_id": "bonus-only",
        "description": "岗位职责：维护后端。\\n加分项：RAG 或 Milvus 项目经验优先。",
    }
    included, _ = baseline_job(eligible)
    excluded, _ = baseline_job(bonus_only)
    assert included["in_scope"]
    milvus_mentions = [m for m in included["technologies"] if m["technology"] == "vector_retrieval"]
    assert {m["requirement_level"] for m in milvus_mentions} == {"required", "preferred"}
    assert all(m["matched_text"] == "Milvus" for m in milvus_mentions)
    assert excluded["in_scope"] is False
    assert excluded["technologies"] == []
    category = next(c for c in aggregate([included, excluded])["categories"]
                    if c["technology"] == "vector_retrieval")
    assert category["job_count"] == 1
    assert category["condition_job_counts"]["required"] == 1
    assert category["condition_job_counts"]["preferred"] == 1


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
    assert not any(f["job_id"] == "fx01" and f.get("technology") == "vector_retrieval"
                   for f in result["failures"])
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
    assert result["jobs"] == len(load_dataset(ROOT / "data" / "jobs.csv"))
    assert result["matched"] > 0
    assert result["verified"] is False
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["retrieval"] == "not_applicable"
    assert manifest["semantic_verification"] is False
    assert len(read_jsonl(output / "predictions.jsonl")) == result["jobs"]
    assert not (output / "evaluation.json").exists()


def test_unified_cli_runs_task_and_keeps_legacy_parser(monkeypatch, capsys, tmp_path):
    import sys
    from experiments.cli import main
    output = tmp_path / "cli-run"
    monkeypatch.setattr(sys, "argv", [
        "job-rag-experiment", "run", "--dataset", str(DATASET), "--gold", str(GOLD),
        "--output", str(output),
    ])
    main()
    assert "matched" in capsys.readouterr().out
    assert (output / "evaluation.json").is_file()
    review = tmp_path / "cli-review"
    monkeypatch.setattr(sys, "argv", [
        "job-rag-experiment", "prepare-review", "--dataset", str(DATASET),
        "--limit", "3", "--output", str(review),
    ])
    main()
    assert len(read_jsonl(review / "review_queue.jsonl")) == 3
