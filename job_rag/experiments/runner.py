"""Frozen offline experiments: no live database or production index writes."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace

import numpy as np

from ..chunking import CHUNKING_VERSION, PARSER_VERSION, build_documents, parse_sections
from ..ingest import parse_csv
from ..normalize import digest, normalize
from ..search import SearchRequest, bm25, matches, tokens
from .metrics import mean_metrics, paired_bootstrap, ranking_metrics

ARMS = {
    "A_legacy_1100": ("legacy", 1100),
    "B_fixed_compact_1100": ("fixed_compact", 1100),
    "C_section_compact_1100": ("section_compact", 1100),
    "D_section_typed_1100": ("section_typed", 1100),
    "E_section_typed_600": ("section_typed", 600),
}
RERANK_INSTRUCTION = (
    "Retrieve recruitment jobs that satisfy the user's intent and explicit constraints. "
    "Distinguish mandatory requirements from preferred qualifications, preserve negation and alternatives, "
    "and prefer concrete job responsibilities over company introductions. Do not interpret non-AI agent roles as AI engineering."
)
QUERY_FILTERS = {"city", "district", "min_salary", "max_salary", "salary_period", "salary_mode",
                 "experience_years", "education", "employment_type", "skills"}


def filter_request(filters):
    if set(filters) - QUERY_FILTERS:
        raise ValueError("Unsupported experiment filter: snapshots do not assert live job status or run query inference")
    return SearchRequest(**filters, infer_filters=False)


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def read_lines(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_lines(path, records):
    Path(path).write_text("".join(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n" for record in records))


def new_directory(path):
    os.umask(0o077)
    path = Path(path)
    path.mkdir(parents=True, exist_ok=False)
    return path


def implementation_hash():
    return digest({name: Path(__file__).parents[1].joinpath(name).read_text()
                   for name in ["chunking.py", "normalize.py", "search.py", "experiments/runner.py", "experiments/bailian.py", "experiments/metrics.py"]})


def validate_benchmark(benchmark, rows):
    by_id = {row["job_id"]: row for row in rows}
    ids, groups = set(), {}
    for query in benchmark["queries"]:
        qid = query["id"]
        if qid in ids or query["split"] not in {"dev", "test"} or not query["text"].strip():
            raise ValueError("Duplicate/invalid benchmark query")
        ids.add(qid)
        group = query["group"]
        if group in groups and groups[group] != query["split"]:
            raise ValueError("Paraphrases from one query group must not cross dev/test splits")
        groups[group] = query["split"]
        request = filter_request(query.get("filters", {}))
        scope = query.get("judgment_scope", "seed")
        if scope not in {"seed", "pooled", "exhaustive"}:
            raise ValueError("Invalid judgment scope")
        if scope != "seed" and not query.get("reviewed"):
            raise ValueError("Non-seed benchmark judgments must be explicitly reviewed")
        if scope == "exhaustive":
            eligible = {job_id for job_id, row in by_id.items() if row["description"].strip()
                        and matches(SimpleNamespace(raw=row, normalized=normalize(row)), request)}
            if set(query.get("qrels", {})) != eligible:
                raise ValueError("Exhaustive benchmark must judge every eligible job")
        if not query.get("qrels"):
            raise ValueError("Each seed query needs at least one source-backed reference")
        for job_id, judgment in query["qrels"].items():
            if job_id not in by_id or type(judgment["grade"]) is not int or judgment["grade"] not in {0, 1, 2, 3}:
                raise ValueError("Unknown job ID or invalid grade in benchmark")
            row = by_id[job_id]
            quote = judgment.get("evidence", "")
            if judgment["grade"] > 0 and (not quote or quote not in row["description"]):
                raise ValueError(f"Reference evidence does not match source for {qid}/{job_id}")
            if judgment["grade"] > 0 and not matches(SimpleNamespace(raw=row, normalized=normalize(row)), request):
                raise ValueError(f"Reference violates explicit hard filters for {qid}/{job_id}")
    if not ids:
        raise ValueError("Empty benchmark")


def prepare(csv_path, benchmark_path, output):
    raw_csv = Path(csv_path).read_bytes()
    rows = parse_csv(raw_csv)
    benchmark = read_json(benchmark_path)
    validate_benchmark(benchmark, rows)
    directory = new_directory(output)
    artifacts = {}
    records = [{"raw": row, "normalized": normalize(row)} for row in rows if row["description"].strip()]
    write_lines(directory / "records.jsonl", records)
    write_json(directory / "benchmark.json", benchmark)
    arms = {}
    for name, (strategy, size) in ARMS.items():
        docs = []
        for row in rows:
            for ordinal, document in enumerate(build_documents(row, strategy=strategy, size=size)):
                docs.append({"chunk_id": digest([name, row["job_id"], ordinal, document.text])[:24],
                             "job_id": row["job_id"], "text": document.text, "details": document.details})
        filename = name + ".jsonl"
        write_lines(directory / filename, docs)
        arms[name] = {"strategy": strategy, "size": size, "budget_unit": "chars", "file": filename,
                      "chunks": len(docs), "input_characters": sum(len(doc["text"]) for doc in docs),
                      "input_utf8_bytes": sum(len(doc["text"].encode()) for doc in docs),
                      "unknown_sections": sum(doc["details"]["section_type"] == "unknown" for doc in docs),
                      "hard_split_chunks": sum(doc["details"]["hard_split"] for doc in docs)}
        artifacts[filename] = digest(docs)
    artifacts["records.jsonl"] = digest(records)
    artifacts["benchmark.json"] = digest(benchmark)
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "csv_sha256": __import__("hashlib").sha256(raw_csv).hexdigest(),
                "parser_version": PARSER_VERSION, "chunking_version": CHUNKING_VERSION,
                "implementation_hash": implementation_hash(),
                "jobs": len(records), "queries": len(benchmark["queries"]), "arms": arms, "artifacts": artifacts,
                "notes": ["No API calls were made during preparation", "Character budgets are NOT Qwen tokenizer counts",
                          "A→B isolates repeated metadata; C→D keeps identical spans and changes condition hints",
                          "D→E is a separate chunk-budget ablation", "Unknown source status is not proof of active recruitment"]}
    write_json(directory / "manifest.json", manifest)
    return manifest


def load_prepared(directory):
    directory = Path(directory)
    manifest = read_json(directory / "manifest.json")
    if manifest["implementation_hash"] != implementation_hash():
        raise ValueError("Experiment implementation changed since preparation; create a new prepared snapshot (embedding cache can be reused)")
    for filename, expected in manifest["artifacts"].items():
        value = read_lines(directory / filename) if filename.endswith(".jsonl") else read_json(directory / filename)
        if digest(value) != expected:
            raise ValueError("Prepared artifact changed; create a new experiment instead of overwriting snapshots")
    return manifest, read_lines(directory / "records.jsonl"), read_json(directory / "benchmark.json")


def _scope(query):
    return query.get("judgment_scope", "seed")


def _grades(query):
    return {job_id: judgment["grade"] for job_id, judgment in query["qrels"].items()}


def _summary(results, strategies, mode):
    summary = {"mode": mode, "by_split": {}, "comparisons": {}, "sample_counts": {}, "adjacent_comparisons": {}}
    for split in ["dev", "test"]:
        selected = [result for result in results if result["split"] == split]
        summary["sample_counts"][split] = {"queries": len(selected), "groups": len({result.get("group", result["query_id"]) for result in selected}),
            "valid_per_metric": {name: {metric: sum(result["metrics"][name].get(metric) is not None for result in selected)
                                        for metric in {key for result in selected for key in result["metrics"][name]}}
                                 for name in strategies}}
        summary["by_split"][split] = {name: mean_metrics([result["metrics"][name] for result in selected]) for name in strategies}
        baseline = strategies[0]
        comparison = {}
        for name in strategies[1:]:
            shared = set(summary["by_split"][split][baseline]) & set(summary["by_split"][split][name])
            comparison[name] = {metric: paired_bootstrap([result["metrics"][baseline].get(metric) for result in selected],
                                                       [result["metrics"][name].get(metric) for result in selected],
                                                       groups=[result.get("group", result.get("query_id")) for result in selected])
                                for metric in sorted(shared) if metric.endswith(("recall@10", "ndcg@5", "precision@5"))}
        summary["comparisons"][split] = {"baseline": baseline, "paired_query_bootstrap": comparison}
        adjacent = {}
        for left, right in zip(strategies, strategies[1:]):
            if right == "BM25_reference":
                continue
            shared = set(summary["by_split"][split][left]) & set(summary["by_split"][split][right])
            adjacent[f"{left} -> {right}"] = {
                metric: paired_bootstrap([result["metrics"][left].get(metric) for result in selected],
                                         [result["metrics"][right].get(metric) for result in selected],
                                         groups=[result.get("group", result.get("query_id")) for result in selected])
                for metric in sorted(shared) if metric.endswith(("recall@10", "ndcg@5", "precision@5"))}
        summary["adjacent_comparisons"][split] = adjacent
    return summary


def recall(prepared, output, client, candidate_limit=50):
    if not 1 <= candidate_limit <= 100:
        raise ValueError("Candidate limit must be 1-100")
    manifest, records, benchmark = load_prepared(prepared)
    directory = new_directory(output)
    by_id = {record["raw"]["job_id"]: record for record in records}
    query_vectors = np.asarray(client.embed([query["text"] for query in benchmark["queries"]], "query"), dtype=np.float64)
    query_vectors /= np.linalg.norm(query_vectors, axis=1, keepdims=True)
    results = []
    for query in benchmark["queries"]:
        request = filter_request(query.get("filters", {}))
        eligible = {job_id for job_id, record in by_id.items() if matches(SimpleNamespace(**record), request)}
        impossible = {job_id for job_id, grade in _grades(query).items() if grade > 0} - eligible
        if impossible:
            raise ValueError("Positive qrels do not satisfy the experiment's hard constraints")
        results.append({"query_id": query["id"], "query": query["text"], "split": query["split"],
                        "group": query["group"], "filters": query.get("filters", {}), "eligible_jobs": len(eligible),
                        "judgment_scope": _scope(query), "qrels": query["qrels"], "rankings": {}, "metrics": {}})
    for arm, settings in manifest["arms"].items():
        docs = read_lines(Path(prepared) / settings["file"])
        started = time.monotonic()
        vectors = np.asarray(client.embed([doc["text"] for doc in docs], "document"), dtype=np.float64)
        if not np.isfinite(vectors).all() or np.any(np.linalg.norm(vectors, axis=1) == 0):
            raise ValueError("Invalid cached/document vectors")
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        similarities = query_vectors @ vectors.T
        arm_rankings = []
        for index, (query, result) in enumerate(zip(benchmark["queries"], results)):
            request = filter_request(query.get("filters", {}))
            eligible = {job_id for job_id, record in by_id.items() if matches(SimpleNamespace(**record), request)}
            best = {}
            for doc, similarity in zip(docs, similarities[index]):
                job_id = doc["job_id"]
                if job_id in eligible and (job_id not in best or float(similarity) > best[job_id]["score"]):
                    best[job_id] = {"job_id": job_id, "score": float(similarity), "chunk_id": doc["chunk_id"],
                                    "source_start": doc["details"]["source_start"], "source_end": doc["details"]["source_end"]}
            ranking = sorted(best.values(), key=lambda item: (-item["score"], item["job_id"]))[:candidate_limit]
            result["rankings"][arm] = ranking
            result["metrics"][arm] = ranking_metrics([item["job_id"] for item in ranking], _grades(query), judgment_scope=_scope(query))
            arm_rankings.append({"query_id": query["id"], "ranking": ranking})
        write_lines(directory / f"{arm}.candidates.jsonl", arm_rankings)
        write_json(directory / f"{arm}.stats.json", {"embedding_and_scoring_seconds": time.monotonic() - started,
                                                    "chunks": len(docs), "job_aggregation": "max chunk cosine, before top-M truncation"})
    # A lexical reference is separate from all dense-only ablation arms.
    lexical_texts = [record["raw"]["title"] + "\n" + record["raw"]["description"] for record in records]
    for query, result in zip(benchmark["queries"], results):
        scores = bm25(tokens(query["text"]), lexical_texts)
        request = filter_request(query.get("filters", {}))
        ranking = [{"job_id": record["raw"]["job_id"], "score": float(score)} for record, score in zip(records, scores)
                   if score > 0 and matches(SimpleNamespace(**record), request)]
        ranking.sort(key=lambda item: (-item["score"], item["job_id"]))
        result["rankings"]["BM25_reference"] = ranking[:candidate_limit]
        result["metrics"]["BM25_reference"] = ranking_metrics([item["job_id"] for item in ranking[:candidate_limit]], _grades(query), judgment_scope=_scope(query))
    write_lines(directory / "results.jsonl", results)
    run_manifest = {"phase": "recall", "prepared_directory": str(Path(prepared).resolve()), "prepared_manifest_hash": digest(manifest),
                    "candidate_limit": candidate_limit, "provider": client.config.public(), "results_hash": digest(results),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "request_journal": str(getattr(client, "journal", "fixture-only")),
                    "cache_path": getattr(client, "cache_path", "fixture-only"),
                    "http_requests_this_run": getattr(client, "requests", None),
                    "cost_guard_cny": getattr(client, "max_cost_cny", None),
                    "estimated_list_cost_cny": getattr(client, "estimated_spend_cny", None),
                    "selection_rule": "Choose on dev only; do not tune on test; no automatic production promotion",
                    "metrics_warning": "Seed recall is known-positive recall, not exhaustive job relevance recall"}
    write_json(directory / "manifest.json", run_manifest)
    summary = _summary(results, list(manifest["arms"]) + ["BM25_reference"], "dense-only recall ablation plus lexical reference")
    write_json(directory / "summary.json", summary)
    return summary


def pool(recall_directory, output, depth=20):
    if not 1 <= depth <= 100:
        raise ValueError("Pool depth must be 1-100")
    manifest = read_json(Path(recall_directory) / "manifest.json")
    _, records, _ = load_prepared(manifest["prepared_directory"])
    results = read_lines(Path(recall_directory) / "results.jsonl")
    if digest(results) != manifest["results_hash"]:
        raise ValueError("Recall results changed")
    by_id = {record["raw"]["job_id"]: record["raw"] for record in records}
    queries = []
    for result in results:
        ids = set(result["qrels"])
        for ranking in result["rankings"].values():
            ids.update(item["job_id"] for item in ranking[:depth])
        queries.append({"id": result["query_id"], "text": result["query"], "split": result["split"], "group": result["group"],
                        "filters": result["filters"], "reviewed": False, "judgment_scope": "pooled", "qrels": {
                            job_id: {"grade": None, "seed_grade": result["qrels"].get(job_id, {}).get("grade"),
                                     "title": by_id[job_id]["title"], "description": by_id[job_id]["description"],
                                     "evidence": "", "reason": ""} for job_id in sorted(ids)}})
    if Path(output).exists():
        raise ValueError("Refusing to overwrite review work")
    write_json(output, {"version": "pooled-review-v1", "pool_depth": depth, "recall_results_hash": manifest["results_hash"], "queries": queries})
    return {"queries": len(queries), "judgments_to_review": sum(len(query["qrels"]) for query in queries)}


def apply_judgments(results, review_path):
    review = read_json(review_path)
    lookup = {query["id"]: query for query in review["queries"]}
    if len(lookup) != len(results):
        raise ValueError("Judgments must cover exactly the frozen query set")
    for result in results:
        query = lookup[result["query_id"]]
        if (not query.get("reviewed") or query["text"] != result["query"] or query["filters"] != result["filters"]
                or query["split"] != result["split"] or query["group"] != result["group"]):
            raise ValueError("Judgments are not reviewed or changed the frozen query/filters")
        depth = review.get("pool_depth", 0)
        if not 1 <= depth <= 100:
            raise ValueError("Review file must record its candidate pool depth")
        expected = set(result["qrels"])
        for ranking in result["rankings"].values():
            expected.update(item["job_id"] for item in ranking[:depth])
        if not expected.issubset(query["qrels"]):
            raise ValueError("Review file dropped pooled candidates; missing candidates are not implicit negatives")
        if query["judgment_scope"] not in {"pooled", "exhaustive"}:
            raise ValueError("Invalid judgment scope")
        for judgment in query["qrels"].values():
            if type(judgment["grade"]) is not int or judgment["grade"] not in {0, 1, 2, 3}:
                raise ValueError("All pooled candidates must receive an explicit grade 0-3")
            if judgment["grade"] > 0 and not judgment.get("evidence"):
                raise ValueError("Positive judgments require evidence")
        result["qrels"], result["judgment_scope"] = query["qrels"], query["judgment_scope"]
    return review


def validate_reviewed_results(results, records):
    by_id = {record["raw"]["job_id"]: record for record in records}
    for result in results:
        request = filter_request(result["filters"])
        eligible = {job_id for job_id, record in by_id.items() if matches(SimpleNamespace(**record), request)}
        if result["judgment_scope"] == "exhaustive" and set(result["qrels"]) != eligible:
            raise ValueError("Exhaustive judgments must label every eligible job, including negatives")
        for job_id, judgment in result["qrels"].items():
            if job_id not in by_id:
                raise ValueError("Reviewed judgment contains an unknown job ID")
            if judgment["grade"] > 0 and (job_id not in eligible or judgment["evidence"] not in by_id[job_id]["raw"]["description"]):
                raise ValueError("Positive reviewed judgment violates constraints or lacks verbatim evidence")


def rescore(recall_directory, judgments, output):
    manifest = read_json(Path(recall_directory) / "manifest.json")
    prepared_manifest, records, _ = load_prepared(manifest["prepared_directory"])
    results = read_lines(Path(recall_directory) / "results.jsonl")
    if digest(results) != manifest["results_hash"] or digest(prepared_manifest) != manifest["prepared_manifest_hash"]:
        raise ValueError("Frozen source artifacts changed")
    review = apply_judgments(results, judgments)
    if review.get("recall_results_hash") != manifest["results_hash"]:
        raise ValueError("Judgments belong to a different recall experiment")
    validate_reviewed_results(results, records)
    for result in results:
        result["metrics"] = {name: ranking_metrics([item["job_id"] for item in ranking],
                             {key: value["grade"] for key, value in result["qrels"].items()}, judgment_scope=result["judgment_scope"])
                             for name, ranking in result["rankings"].items()}
    directory = new_directory(output)
    write_lines(directory / "results.jsonl", results)
    write_json(directory / "manifest.json", {**manifest, "phase": "recall_reviewed", "results_hash": digest(results),
               "source_results_hash": manifest["results_hash"], "judgments_hash": digest(review)})
    summary = _summary(results, list(results[0]["rankings"]), "recall rescored against reviewed judgments, no API calls")
    write_json(directory / "summary.json", summary)
    return summary


def _representation(row, budget=1800):
    """Same bounded, source-based parent representation for every reranking arm."""
    source = row["description"]
    sections = parse_sections(source)
    ordered = sorted(sections, key=lambda section: ({"requirements": 0, "responsibilities": 1, "preferred": 2}.get(section.section_type, 3), section.start))
    rendered = f"岗位：{row['title']}\n"
    if len(rendered.encode()) > budget:
        return rendered.encode()[:budget - 40].decode("utf-8", errors="ignore") + "\n[原文有截断，需完整复核]", True
    truncated = False
    for section in ordered:
        addition = f"\n章节：{section.title}\n" + source[section.start:section.end]
        remaining = budget - len(rendered.encode())
        if len(addition.encode()) > remaining:
            addition = addition.encode()[:max(remaining - 40, 0)].decode("utf-8", errors="ignore") + "\n[原文有截断，需完整复核]"
            rendered += addition
            truncated = True
            break
        rendered += addition
    return rendered, truncated


def rerank(recall_directory, output, client, arm, judgments=None, allow_provisional=False):
    manifest = read_json(Path(recall_directory) / "manifest.json")
    prepared_manifest, records, _ = load_prepared(manifest["prepared_directory"])
    if digest(prepared_manifest) != manifest["prepared_manifest_hash"]:
        raise ValueError("Prepared manifest changed")
    results = read_lines(Path(recall_directory) / "results.jsonl")
    if digest(results) != manifest["results_hash"]:
        raise ValueError("Frozen candidate/results artifact changed")
    if judgments:
        review = apply_judgments(results, judgments)
        if review.get("recall_results_hash") != manifest["results_hash"]:
            raise ValueError("Judgments belong to another recall run")
    elif not allow_provisional:
        raise ValueError("Round 2 requires reviewed pooled judgments; --allow-provisional is diagnostic only")
    if judgments:
        validate_reviewed_results(results, records)
    if any(arm not in result["rankings"] for result in results):
        raise ValueError("Choose a single existing recall arm, based on dev data")
    directory = new_directory(output)
    by_id = {record["raw"]["job_id"]: record["raw"] for record in records}
    outputs = []
    names = ["none", "bm25", "section_rule", "qwen_default", "qwen_recruitment_instruction"]
    for result in results:
        original = result["rankings"][arm]
        ids = [item["job_id"] for item in original]
        budget = min(1800, (110000 - len(result["query"].encode()) * len(ids)) // max(len(ids), 1))
        if budget < 256:
            raise ValueError("Query/candidate count leaves insufficient rerank document budget")
        representations = [_representation(by_id[job_id], budget) for job_id in ids]
        texts = [item[0] for item in representations]
        lexical_scores = bm25(tokens(result["query"]), texts)
        rankings = {"none": ids, "bm25": [ids[i] for i in sorted(range(len(ids)), key=lambda i: (-lexical_scores[i], i))]}
        # Transparent baseline: section role, lexical matching and required/preferred intent.
        rule_scores = []
        for i, job_id in enumerate(ids):
            best = 0.0
            for doc in build_documents(by_id[job_id], strategy="section_typed", size=240):
                if doc.details["raw_text"] not in texts[i]:
                    continue
                weight = {"requirements": 1.2, "responsibilities": 1.0, "preferred": .7}.get(doc.details["section_type"], .4)
                overlap = len(set(tokens(result["query"])) & set(tokens(doc.details["raw_text"])))
                if "必须" in result["query"] and doc.details["requirement_level"] in {"preferred", "mixed", "not_required"}:
                    weight *= .3
                best = max(best, weight * overlap)
            rule_scores.append(best)
        rankings["section_rule"] = [ids[i] for i in sorted(range(len(ids)), key=lambda i: (-rule_scores[i], i))]
        latencies = {}
        for name, instruction in [("qwen_default", ""), ("qwen_recruitment_instruction", RERANK_INSTRUCTION)]:
            start = time.monotonic()
            sorted_results = client.rerank(result["query"], texts, instruction)
            latencies[name] = {"elapsed_ms": (time.monotonic() - start) * 1000,
                               "cache_hit": getattr(client, "last_from_cache", None)}
            rankings[name] = [ids[item["index"]] for item in sorted_results]
        if any(set(ranking) != set(ids) or len(ranking) != len(ids) for ranking in rankings.values()):
            raise ValueError("A reranker changed the frozen candidate set")
        grades = {key: value["grade"] for key, value in result["qrels"].items()}
        outputs.append({"query_id": result["query_id"], "split": result["split"], "group": result["group"], "query": result["query"],
                        "candidate_ids": ids, "representations": [{"job_id": key, "text": text, "truncated": truncated}
                                                                    for key, (text, truncated) in zip(ids, representations)],
                        "representation_budget_utf8_bytes": budget,
                        "rankings": rankings, "latency_ms": latencies, "judgment_scope": result["judgment_scope"],
                        "candidate_recall_ceiling": ranking_metrics(ids, grades, judgment_scope=result["judgment_scope"]),
                        "metrics": {name: ranking_metrics(ranking, grades, judgment_scope=result["judgment_scope"])
                                    for name, ranking in rankings.items()}})
    write_lines(directory / "results.jsonl", outputs)
    write_json(directory / "manifest.json", {"phase": "rerank", "recall_run": str(Path(recall_directory).resolve()),
               "recall_results_hash": manifest["results_hash"], "recall_arm": arm, "provider": client.config.public(),
               "completed_at": datetime.now(timezone.utc).isoformat(),
               "request_journal": str(getattr(client, "journal", "fixture-only")),
               "cache_path": getattr(client, "cache_path", "fixture-only"),
               "http_requests_this_run": getattr(client, "requests", None),
               "cost_guard_cny": getattr(client, "max_cost_cny", None),
               "estimated_list_cost_cny": getattr(client, "estimated_spend_cny", None),
               "judgments_hash": digest(read_json(judgments)) if judgments else None,
               "representation": "frozen parent sections, at most 1800 UTF-8 bytes, identical across arms",
               "provisional": not bool(judgments), "strategies": names})
    summary = _summary(outputs, names, "fixed-candidate rerank; NOT another recall experiment")
    write_json(directory / "summary.json", summary)
    return summary


def report(directory):
    import csv
    directory = Path(directory)
    summary = read_json(directory / "summary.json")
    rows = [{"split": split, "strategy": name, "metric": key, "value": value}
            for split, strategies in summary["by_split"].items() for name, metrics in strategies.items() for key, value in metrics.items()]
    with (directory / "metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["split", "strategy", "metric", "value"])
        writer.writeheader()
        writer.writerows(rows)
    lines = ["# Experiment report", "", summary["mode"], "",
             "Seed/pooled prefixes indicate incomplete relevance judgments. Do not call them exhaustive recall/precision.", "",
             "| Split | Strategy | Metric | Value |", "|---|---|---|---:|"]
    for row in rows:
        lines.append(f"| {row['split']} | {row['strategy']} | {row['metric']} | {row['value']:.6f} |")
    (directory / "report.md").write_text("\n".join(lines) + "\n")
    return {"files": [str(directory / "metrics.csv"), str(directory / "report.md")]}
