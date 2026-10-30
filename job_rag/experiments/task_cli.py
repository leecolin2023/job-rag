"""CLI for the task-first, source-backed RAG requirements experiment."""
import argparse
import json

from .task_runner import run
from .task_eval import evaluate
from .task_review import prepare_review_queue


def main():
    parser = argparse.ArgumentParser(description="Task-first RAG job requirements experiments (no paid APIs)")
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("run", help="Run a fresh exhaustive literal/rule baseline")
    start.add_argument("--dataset", required=True, help="Source jobs.csv or synthetic fixtures.json")
    start.add_argument("--output", required=True, help="New run directory; will not overwrite")
    start.add_argument("--gold", help="Optional separately authored fixture or human-reviewed gold.jsonl")
    review = commands.add_parser("prepare-review", help="Create an unreviewed, stratified JD queue (NOT gold)")
    review.add_argument("--dataset", required=True)
    review.add_argument("--output", required=True)
    review.add_argument("--limit", type=int, default=40)
    score = commands.add_parser("evaluate", help="Score source-backed predictions with first-failure diagnostics")
    score.add_argument("--run", required=True, help="Directory containing frozen manifest and traces")
    score.add_argument("--dataset", required=True, help="Exactly the same source snapshot as the run")
    score.add_argument("--gold", required=True)
    score.add_argument("--predictions", help="Optional external Agent/LLM predictions.jsonl")
    score.add_argument("--trace", help="Optional external per-stage trace.jsonl; missing stages stay undetermined")
    args = parser.parse_args()
    try:
        if args.command == "run":
            result = run(args.dataset, args.output)
            if args.gold:
                result["evaluation"] = evaluate(args.output, args.dataset, args.gold)
        elif args.command == "prepare-review":
            result = prepare_review_queue(args.dataset, args.output, args.limit)
        else:
            result = evaluate(args.run, args.dataset, args.gold, args.predictions, args.trace)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Experiment failed: {exc}\n")


if __name__ == "__main__":
    main()
