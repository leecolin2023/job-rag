"""Summarize real request journals without reading API keys or printing bodies.

List-price estimates are not account bills: credits/free quota/provider billing
changes are outside this script's visibility. Parsing failures after HTTP 200 may
still be billed and are intentionally included.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import statistics

from job_rag.experiments.bailian import PRICES_CNY_PER_MILLION


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--journal", help="One exact journal file; default: all experiment request journals")
    args = parser.parse_args()
    paths = [Path(args.journal)] if args.journal else sorted(Path("runtime/experiments/requests").glob("*.jsonl"))
    groups = defaultdict(list)
    for path in paths:
        for line in path.read_text().splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                # A concurrently running writer may not have completed its last line.
                continue
            groups[record["model"]].append(record)
    result = {}
    for model, records in groups.items():
        count = sum(record.get("usage", {}).get("total_tokens", 0) for record in records)
        price = PRICES_CNY_PER_MILLION.get(model)
        latencies = sorted(record["latency_ms"] for record in records if record.get("status") == 200)
        result[model] = {"http_requests": len(records), "statuses": dict(Counter(str(record.get("status", "transport_error")) for record in records)),
                         "reported_input_tokens": count, "usage_based_list_estimate_cny": count * price / 1_000_000 if price is not None else None,
                         "requests_without_reported_usage": sum("total_tokens" not in record.get("usage", {}) for record in records),
                         "http_latency_median_ms": statistics.median(latencies) if latencies else None,
                         "http_latency_p95_ms": latencies[min(len(latencies) - 1, int(len(latencies) * .95))] if latencies else None}
    print(json.dumps({"models": result, "journal_files": len(paths), "not_an_account_bill": True}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
