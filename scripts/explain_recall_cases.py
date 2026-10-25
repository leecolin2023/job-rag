"""Audit frozen per-query rankings without any API calls or relevance relabeling."""
import argparse
import csv
import json
import os
from pathlib import Path

from job_rag.experiments.runner import load_prepared, read_json, read_lines, write_json
from job_rag.normalize import digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="runtime/experiments/recall-20261025-v1")
    parser.add_argument("--output", default="runtime/analysis/recall-case-audit-20261025")
    args = parser.parse_args()
    run = Path(args.run)
    manifest = read_json(run / "manifest.json")
    prepared, records, _ = load_prepared(manifest["prepared_directory"])
    results = read_lines(run / "results.jsonl")
    if digest(results) != manifest["results_hash"] or digest(prepared) != manifest["prepared_manifest_hash"]:
        raise ValueError("Frozen experiment integrity check failed")
    by_id = {record["raw"]["job_id"]: record["raw"] for record in records}
    chunks = {}
    for name, arm in prepared["arms"].items():
        chunks[name] = {chunk["chunk_id"]: chunk for chunk in read_lines(Path(manifest["prepared_directory"]) / arm["file"])}
    os.umask(0o077)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    cases, table = [], []
    for result in results:
        positives = {job_id for job_id, judgment in result["qrels"].items() if judgment["grade"] > 0}
        case = {"query_id": result["query_id"], "split": result["split"], "query": result["query"],
                "filters": result["filters"], "eligible_jobs": result["eligible_jobs"], "known_positive_only": True,
                "seeds": [{"job_id": job_id, "title": by_id[job_id]["title"], "url": by_id[job_id]["url"],
                           "evidence": judgment["evidence"]} for job_id, judgment in result["qrels"].items()], "methods": {}}
        for arm, ranking in result["rankings"].items():
            positions = {item["job_id"]: i + 1 for i, item in enumerate(ranking)}
            seed_ranks = {job_id: positions.get(job_id) for job_id in positives}
            top = []
            for position, item in enumerate(ranking[:5], 1):
                raw = by_id[item["job_id"]]
                evidence = chunks.get(arm, {}).get(item.get("chunk_id"))
                top.append({"rank": position, "job_id": item["job_id"], "title": raw["title"], "url": raw["url"],
                            "score": item["score"], "is_seed": item["job_id"] in positives,
                            "matched_chunk": evidence["text"] if evidence else None,
                            "source_description": raw["description"]})
            best = min((value for value in seed_ranks.values() if value is not None), default=None)
            case["methods"][arm] = {"seed_ranks": seed_ranks, "best_seed_rank": best, "top5": top}
            table.append({"query_id": result["query_id"], "split": result["split"], "query": result["query"],
                          "eligible_jobs": result["eligible_jobs"], "method": arm, "best_seed_rank": best,
                          "top1_title": top[0]["title"] if top else "", "top1_job_id": top[0]["job_id"] if top else ""})
        cases.append(case)
    write_json(output / "cases.json", {"source_results_hash": manifest["results_hash"],
               "warning": "Seed rank is not complete relevance. Non-seed candidates are unjudged, not negatives. BM25 and cosine scores are not comparable.",
               "cases": cases})
    with (output / "rankings.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)
    short = ["A_legacy_1100", "C_section_compact_1100", "D_section_typed_1100", "BM25_reference"]
    lines = ["# 30条查询逐项核对", "", "不重新请求模型，不修改标签。排名仅针对已知正例，未标注岗位不等于不相关。", "",
             "A=原固定分块向量；C=章节紧凑向量；D=章节+条件提示向量；BM25=全岗位词法参考。", "",
             "| 查询 | split | 完整问题 | A | C | D | BM25 |", "|---|---|---|---:|---:|---:|---:|"]
    for case in cases:
        ranks = [str(case["methods"][name]["best_seed_rank"] or ">50") for name in short]
        lines.append("| " + " | ".join([case["query_id"], case["split"], case["query"].replace("|", "／")] + ranks) + " |")
    for case in cases:
        lines.extend(["", f"## {case['query_id']}", "", case["query"], "",
                      f"硬条件：`{json.dumps(case['filters'], ensure_ascii=False)}`；eligible岗位：{case['eligible_jobs']}。", ""])
        for seed in case["seeds"]:
            lines.extend([f"已知正例：{seed['title']}（`{seed['job_id']}`）", "", f"原文依据：{seed['evidence']}", ""])
        for name in short:
            method = case["methods"][name]
            lines.extend([f"### {name}；已知正例排名：{method['best_seed_rank'] or '>50'}", ""])
            for top in method["top5"][:3]:
                lines.append(f"{top['rank']}. {top['title']} — `{top['job_id']}` {'（已知正例）' if top['is_seed'] else '（未完整标注）'}")
            if name == "C_section_compact_1100" and method["top5"]:
                lines.extend(["", "实际Top-1命中块（原始保存结果）：", "", "```text", method["top5"][0]["matched_chunk"] or "", "```", ""])
    (output / "cases.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"queries": len(cases), "files": [str(output / name) for name in ["cases.md", "rankings.csv", "cases.json"]],
                      "api_calls": 0, "integrity_check": "PASS"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
