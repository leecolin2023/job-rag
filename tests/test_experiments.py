import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.metrics import paired_bootstrap, ranking_metrics
from experiments.runner import (
    ARMS, audit_rerank_inputs, load_prepared, pool, prepare, read_json, read_lines, recall, report, rerank, rescore, write_json,
)

from conftest import csv_bytes, row


class FixtureClient:
    """Synthetic unit-test vectors. NEVER used to claim real Qwen quality."""
    config = SimpleNamespace(public=lambda: {"model": "synthetic_fixture_only"})

    def embed(self, texts, text_type):
        return [[1., float("RAG" in text), float("Java" in text), float("Python" in text)] for text in texts]

    def rerank(self, query, documents, instruct=""):
        return [{"index": i, "relevance_score": float(i)} for i in reversed(range(len(documents)))]


def fixture_prepare(tmp_path):
    csv = tmp_path / "jobs.csv"
    csv.write_bytes(csv_bytes(row(), row("two", title="Java开发", description="Java开发与测试")))
    benchmark = {"queries": [
        {"id": "q1", "group": "g1", "split": "dev", "text": "RAG Python", "qrels": {
            "one": {"grade": 3, "evidence": "Python"}}},
        {"id": "q2", "group": "g2", "split": "test", "text": "Java", "qrels": {
            "two": {"grade": 3, "evidence": "Java开发"}}},
    ]}
    source = tmp_path / "benchmark.json"
    write_json(source, benchmark)
    prepared = tmp_path / "prepared"
    prepare(csv, source, prepared)
    return prepared


def test_metrics_do_not_present_seed_labels_as_exhaustive_recall():
    result = ranking_metrics(["a", "b", "c"], {"a": 3, "x": 2})
    assert result["seed_recall@3"] == .5
    assert "recall@3" not in result
    assert "precision@3" not in result
    assert result["precision_lower_bound@3"] == 1 / 3
    assert result["judged_fraction@3"] == 1 / 3
    assert ranking_metrics(["a", "a"], {"a": 3}, judgment_scope="exhaustive")["recall@3"] == 1
    delta = paired_bootstrap([0., 0.], [1., 1.], repeats=100)
    assert delta["ci95"] == [1., 1.]


def test_recall_then_fixed_candidate_rerank_and_review(tmp_path):
    prepared = fixture_prepare(tmp_path)
    recdir = tmp_path / "recall"
    summary = recall(prepared, recdir, FixtureClient(), candidate_limit=2)
    assert "seed_recall@1" in summary["by_split"]["dev"]["A_legacy_1100"]
    results = read_lines(recdir / "results.jsonl")
    assert len(results) == 2
    assert all(len(result["rankings"]) == len(ARMS) + 1 for result in results)
    with pytest.raises(ValueError, match="reviewed"):
        rerank(recdir, tmp_path / "not-reviewed", FixtureClient(), "D_section_typed_1100")
    rerankdir = tmp_path / "rerank-provisional"
    rerank(recdir, rerankdir, FixtureClient(), "D_section_typed_1100", allow_provisional=True)
    for result in read_lines(rerankdir / "results.jsonl"):
        assert all(set(ranking) == set(result["candidate_ids"]) for ranking in result["rankings"].values())
        assert all(not item["truncated"] for item in result["representations"])
    review = tmp_path / "review.json"
    assert pool(recdir, review, depth=2)["judgments_to_review"] == 4
    labels = read_json(review)
    for query in labels["queries"]:
        query["reviewed"] = True
        query["judgment_scope"] = "exhaustive"
        for job_id, judgment in query["qrels"].items():
            positive = job_id == ("one" if query["id"] == "q1" else "two")
            judgment["grade"] = 3 if positive else 0
            judgment["evidence"] = "Python" if query["id"] == "q1" and positive else ("Java" if positive else "")
    write_json(review, labels)
    scored = tmp_path / "rescored"
    rescore(recdir, review, scored)
    assert "recall@1" in read_json(scored / "summary.json")["by_split"]["dev"]["A_legacy_1100"]
    rerank(recdir, tmp_path / "rerank-reviewed", FixtureClient(), "D_section_typed_1100", judgments=review)
    assert len(report(scored)["files"]) == 2


def test_artifact_mutation_is_rejected(tmp_path):
    prepared = fixture_prepare(tmp_path)
    path = prepared / "records.jsonl"
    path.write_text(path.read_text().replace("测试公司", "修改公司"))
    with pytest.raises(ValueError, match="changed"):
        load_prepared(prepared)


def test_full_jd_keeps_tail_whitespace_and_original_section_order():
    from experiments.runner import _representation
    description = " \n岗位职责\n" + "负责系统建设。" * 600 + "\r\n任职要求\n不要求博士，满足其一即可。 \n"
    text, truncated = _representation(row(description=description))
    assert text.endswith(description)
    assert len(text.encode()) > 1800
    assert not truncated


def test_audit_and_whole_run_preflight_do_not_call_model(tmp_path):
    prepared = fixture_prepare(tmp_path)
    recdir = tmp_path / "recall"
    recall(prepared, recdir, FixtureClient(), candidate_limit=2)
    audit = audit_rerank_inputs(recdir)
    assert len(audit["requests"]) == 2 * (len(ARMS) + 1) * 2
    assert all(item["admitted"] for item in audit["requests"])
    # Historical implementation may differ; frozen source/candidate hashes may not.
    prepared_manifest = read_json(prepared / "manifest.json")
    prepared_manifest["implementation_hash"] = "historical-implementation"
    write_json(prepared / "manifest.json", prepared_manifest)
    from job_rag.preprocessing.normalize import digest
    manifest = read_json(recdir / "manifest.json")
    manifest["prepared_manifest_hash"] = digest(prepared_manifest)
    write_json(recdir / "manifest.json", manifest)
    assert audit_rerank_inputs(recdir)["requests"] == audit["requests"]
    # A later overlong query must stop the whole run before its first API call.
    results = read_lines(recdir / "results.jsonl")
    results[-1]["query"] = "x" * 4001
    from experiments.runner import write_lines
    from job_rag.preprocessing.normalize import digest
    write_lines(recdir / "results.jsonl", results)
    manifest = read_json(recdir / "manifest.json")
    manifest["results_hash"] = digest(results)
    write_json(recdir / "manifest.json", manifest)

    class NoCalls(FixtureClient):
        def rerank(self, *args, **kwargs):
            pytest.fail("preflight must run before model calls")

    with pytest.raises(ValueError, match="No text was truncated"):
        rerank(recdir, tmp_path / "blocked", NoCalls(), "A_legacy_1100", allow_provisional=True)
    assert not (tmp_path / "blocked").exists()


def test_reference_evidence_and_paraphrase_splits_are_validated(tmp_path):
    prepared = fixture_prepare(tmp_path)
    benchmark = read_json(prepared / "benchmark.json")
    benchmark["queries"][1]["group"] = "g1"
    bad = tmp_path / "bad.json"
    write_json(bad, benchmark)
    with pytest.raises(ValueError, match="cross"):
        prepare(tmp_path / "jobs.csv", bad, tmp_path / "bad-prepared")


def test_seed_set_cannot_be_mislabeled_as_exhaustive(tmp_path):
    prepared = fixture_prepare(tmp_path)
    benchmark = read_json(prepared / "benchmark.json")
    benchmark["queries"][0].update(judgment_scope="exhaustive", reviewed=True)
    bad = tmp_path / "bad-exhaustive.json"
    write_json(bad, benchmark)
    with pytest.raises(ValueError, match="every eligible"):
        prepare(tmp_path / "jobs.csv", bad, tmp_path / "bad-prepared")


def test_real_benchmark_has_thirty_source_backed_queries(tmp_path):
    root = Path(__file__).resolve().parents[1]
    manifest = prepare(root / "data/jobs.csv", root / "experiments/benchmark.v1.json", tmp_path / "real")
    from job_rag.preprocessing.validation import parse_csv
    expected_jobs = sum(bool(row["description"].strip()) for row in parse_csv((root / "data/jobs.csv").read_bytes()))
    assert manifest["jobs"] == expected_jobs
    assert manifest["queries"] == 30
    assert manifest["arms"]["A_legacy_1100"]["chunks"] >= expected_jobs
    assert manifest["arms"]["A_legacy_1100"]["chunks"] == len(read_lines(tmp_path / "real" / "A_legacy_1100.jsonl"))
    assert manifest["arms"]["C_section_compact_1100"]["chunks"] == manifest["arms"]["D_section_typed_1100"]["chunks"]
    for record in read_lines(tmp_path / "real" / "D_section_typed_1100.jsonl"):
        assert len(record["text"]) <= 1100


def test_jsonl_readers_preserve_unicode_line_separator_inside_jd(tmp_path):
    from experiments.runner import write_lines, read_lines
    from experiments.rag_tech_requirements.task_runner import write_jsonl, read_jsonl
    rows = [{"job_id": "unicode", "text": "岗位职责：RAG\u2028任职要求：Python\u2029更多内容\u0085结尾"}]
    ranking_jsonl = tmp_path / "ranking.jsonl"
    write_lines(ranking_jsonl, rows)
    assert read_lines(ranking_jsonl) == rows
    task_jsonl = tmp_path / "task.jsonl"
    write_jsonl(task_jsonl, rows)
    assert read_jsonl(task_jsonl) == rows
