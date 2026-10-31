import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from .bailian import BailianClient, BailianConfig, BailianError
from .runner import ARMS, audit_rerank_inputs, pool, prepare, recall, rerank, rescore, report
from .task_runner import run as run_task
from .task_eval import evaluate as evaluate_task
from .task_review import prepare_review_queue


def main():
    parser = argparse.ArgumentParser(description="Job-RAG offline experiments: retrieval rankings and business task evaluations")
    parser.add_argument("--env-file", default=".env.experiments")
    parser.add_argument("--cache", default="runtime/experiments/cache.sqlite3")
    parser.add_argument("--max-requests", type=int, default=1000)
    parser.add_argument("--max-cost-cny", type=float, help="Conservative software guard using published Beijing list prices, not a provider billing limit")
    commands = parser.add_subparsers(dest="command", required=True)
    task = commands.add_parser("run", help="Run a full-corpus task baseline (no paid APIs)")
    task.add_argument("--dataset", required=True)
    task.add_argument("--output", required=True)
    task.add_argument("--gold", help="Optional separately authored gold labels")
    review = commands.add_parser("prepare-review", help="Create unreviewed real-JD annotation queue")
    review.add_argument("--dataset", required=True)
    review.add_argument("--output", required=True)
    review.add_argument("--limit", type=int, default=40)
    evaluation = commands.add_parser("evaluate", help="Score task predictions with independent gold")
    evaluation.add_argument("--run", required=True)
    evaluation.add_argument("--dataset", required=True)
    evaluation.add_argument("--gold", required=True)
    evaluation.add_argument("--predictions", help="Optional external predictions JSONL")
    evaluation.add_argument("--trace", help="Optional external run trace JSONL")
    evaluation.add_argument("--output", help="New score directory required for external predictions")
    prep = commands.add_parser("prepare", help="Freeze corpus, benchmark and ablation arms; no API calls")
    prep.add_argument("--csv", default="data/jobs.csv")
    prep.add_argument("--benchmark", default="experiments/benchmark.v1.json")
    prep.add_argument("--output", required=True)
    rec = commands.add_parser("recall", help="Round 1: dense-only recall, no rerank/query rewriting")
    rec.add_argument("--prepared", required=True)
    rec.add_argument("--output", required=True)
    rec.add_argument("--candidate-limit", type=int, default=50)
    rec.add_argument("--execute", action="store_true", help="Acknowledge external API calls and billing")
    judge = commands.add_parser("pool", help="Produce judgments without strategy/rank identifiers; no API calls")
    judge.add_argument("--recall-run", required=True)
    judge.add_argument("--depth", type=int, default=20)
    judge.add_argument("--output", required=True)
    score = commands.add_parser("rescore", help="Re-evaluate existing recall rankings using reviewed labels, without API calls")
    score.add_argument("--recall-run", required=True)
    score.add_argument("--judgments", required=True)
    score.add_argument("--output", required=True)
    rank = commands.add_parser("rerank", help="Round 2: compare rerankers on one frozen recall arm")
    rank.add_argument("--recall-run", required=True)
    rank.add_argument("--arm", required=True)
    rank.add_argument("--judgments")
    rank.add_argument("--allow-provisional", action="store_true")
    rank.add_argument("--output", required=True)
    rank.add_argument("--execute", action="store_true")
    render = commands.add_parser("report", help="Render summary JSON to Markdown and CSV; no API calls")
    render.add_argument("run")
    audit = commands.add_parser("audit-rerank-inputs", help="Inspect full-JD frozen candidate request sizes; no API calls or credentials")
    audit.add_argument("--recall-run", required=True)
    audit.add_argument("--model", default="qwen3.7-text-rerank")
    audit.add_argument("--tokenizer-path", default="", help="Local tokenizer JSON; caller must verify suitability for the hosted model")
    probe = commands.add_parser("probe", help="Tiny paid model/endpoint/auth validation before a full run")
    probe.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    client = None
    try:
        if args.max_requests < 1:
            raise ValueError("max-requests must be positive")
        if args.command == "run":
            result = run_task(args.dataset, args.output)
            if args.gold:
                result["evaluation"] = evaluate_task(args.output, args.dataset, args.gold)
        elif args.command == "prepare-review":
            result = prepare_review_queue(args.dataset, args.output, args.limit)
        elif args.command == "evaluate":
            result = evaluate_task(args.run, args.dataset, args.gold, args.predictions, args.trace, args.output)
        elif args.command == "prepare":
            result = prepare(args.csv, args.benchmark, args.output)
        elif args.command == "pool":
            result = pool(args.recall_run, args.output, args.depth)
        elif args.command == "rescore":
            result = rescore(args.recall_run, args.judgments, args.output)
        elif args.command == "report":
            result = report(args.run)
        elif args.command == "audit-rerank-inputs":
            result = audit_rerank_inputs(args.recall_run, args.model, args.tokenizer_path)
        else:
            if not args.execute:
                parser.error("This command calls paid APIs. Use --execute only after reviewing the prepared plan")
            config = BailianConfig.load(args.env_file)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            journal = Path("runtime/experiments/requests") / f"{stamp}.jsonl"
            cache = args.cache if args.command != "probe" else f"runtime/experiments/probes/{stamp}.sqlite3"
            client = BailianClient(config, cache, journal, max_requests=args.max_requests, max_cost_cny=args.max_cost_cny)
            if args.command == "recall":
                result = recall(args.prepared, args.output, client, args.candidate_limit)
            elif args.command == "rerank":
                result = rerank(args.recall_run, args.output, client, args.arm, args.judgments, args.allow_provisional)
            else:
                vectors = client.embed(["企业知识库 RAG 检索增强生成工程师"], "query")
                ranked = client.rerank("企业知识库开发岗位", ["负责 RAG 知识库检索开发。", "负责航空旅客票务服务。"])
                result = {"ok": True, "embedding_dimensions": len(vectors[0]), "rerank_indices": [item["index"] for item in ranked],
                          "requests": client.requests, "journal": str(journal)}
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except (ValueError, BailianError, OSError, KeyError, json.JSONDecodeError) as exc:
        # BailianError messages are intentionally safe. No provider body/key is printed.
        parser.exit(1, f"实验未完成：{exc}\n")
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    main()
