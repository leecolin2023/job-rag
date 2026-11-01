"""Reproduce the supplied CSV question via import/index and real MCP/API calls.

Run from repository root: .venv/bin/python experiments/rag_tech_requirements/scripts/run_pipeline.py
    --output runtime/experiments/rag-tech-YYYYMMDD
No production database changes or paid provider calls. Each response is archived.
"""
import argparse
import asyncio
from collections import Counter, defaultdict
import csv
from dataclasses import replace
from datetime import datetime, timezone
import io
import json
import logging
from pathlib import Path
import socket
import time
import threading

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
import uvicorn

from job_rag.config import Settings
from job_rag.interfaces.api import create_app
from job_rag.interfaces.mcp_server import create_mcp
from job_rag.preprocessing.importer import import_csv
from job_rag.indexing.worker import run_index_tasks
from job_rag.storage import Database


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def prepare_csv(csv_path, output):
    settings = Settings(database_url=f"sqlite:///{output.resolve() / 'analysis.db'}",
        embedding_api_key="", embedding_model="", chat_api_key="", chat_model="",
        rerank_api_key="", rerank_model="", admin_token="")
    db = Database(settings)
    db.initialize()
    try:
        imported = import_csv(db, settings, csv_path.read_bytes(), "boss")
        indexed = run_index_tasks(db, settings)
        if indexed["failed"] or imported.get("failed", 0):
            raise RuntimeError("Import/index failed; inspect setup.json")
        write_json(output / "setup.json", {"import": imported, "index": indexed,
            "index_signature": settings.index_signature, "chunking_strategy": settings.chunking_strategy,
            "chunk_size": settings.chunk_size, "chunk_budget_unit": settings.chunk_budget_unit})
    finally:
        db.engine.dispose()
    return settings


async def acceptance(output, settings):
    api_port, mcp_port = free_port(), free_port()
    api = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1", port=api_port, log_level="error"))
    mcp = uvicorn.Server(uvicorn.Config(create_mcp(f"http://127.0.0.1:{api_port}").streamable_http_app(),
                                        host="127.0.0.1", port=mcp_port, log_level="error"))
    # MCP sync tool handlers perform blocking HTTP calls. The API must have its
    # own event loop so it can answer while the MCP handler is waiting.
    api_thread = threading.Thread(target=api.run, daemon=True)
    api_thread.start()
    tasks = [asyncio.create_task(mcp.serve())]
    trace = []
    try:
        for _ in range(200):
            if api.started and mcp.started:
                break
            if any(t.done() for t in tasks):
                raise RuntimeError("Isolated server failed to start")
            await asyncio.sleep(.05)
        else:
            raise RuntimeError("Isolated server startup timed out")
        def factory(**kwargs):
            return httpx.AsyncClient(**kwargs, trust_env=False)
        async with streamablehttp_client(f"http://127.0.0.1:{mcp_port}/mcp", httpx_client_factory=factory) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                assert names == {"get_knowledge_base_stats", "search_job_candidates", "get_job", "get_jobs_batch",
                                 "query_job_catalog", "summarize_job_technical_mentions"}
                async def call(name, arguments):
                    started = time.monotonic()
                    result = await session.call_tool(name, arguments)
                    assert not result.isError, result
                    data = result.structuredContent or json.loads(next(c.text for c in result.content if c.type == "text"))
                    write_json(output / "calls" / f"{len(trace) + 1:03d}-{name}.json", {"arguments": arguments, "response": data})
                    trace.append({"tool": name, "arguments": arguments, "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
                                  "request_id": data.get("_trace", {}).get("request_id"), "is_error": False})
                    write_json(output / "trace.json", trace)
                    assert data.get("_trace", {}).get("transport") == "mcp_to_api"
                    return data
                stats = await call("get_knowledge_base_stats", {})
                write_json(output / "stats.json", stats)
                broad_args = {"terms": ["RAG"], "fields": ["description"],
                              "aliases": {"RAG": ["GraphRAG", "RAGFlow"]}, "match_mode": "ascii_token",
                              "filters": {"include_closed": True}, "page_size": 100}
                async def enumerate_catalog(args):
                    first_page = await call("query_job_catalog", args)
                    page, records = first_page, []
                    while True:
                        records.extend(page["results"])
                        if not page["has_more"]:
                            break
                        page = await call("query_job_catalog", {**args, "offset": page["next_offset"],
                                                                "snapshot_id": first_page["snapshot_id"]})
                    assert len(records) == len({j["key"] for j in records}) == first_page["matched_jobs"]
                    return first_page, records
                broad, broad_jobs = await enumerate_catalog(broad_args)
                write_json(output / "broad_catalog.json", broad)
                write_json(output / "broad_jobs.json", broad_jobs)
                independent_rag = await call("query_job_catalog", {**broad_args, "aliases": {}, "count_only": True})
                write_json(output / "independent_rag.json", independent_rag)
                all_sections = ["responsibilities", "requirements", "preferred", "company_intro", "benefits", "unknown"]
                broad_summary = await call("summarize_job_technical_mentions", {
                    "terms": ["RAG"], "aliases": broad_args["aliases"], "sections": all_sections,
                    "technical_sections": all_sections, "corpus_id": broad["corpus_id"],
                    "filters": broad_args["filters"], "evidence_samples_per_technology": 1})
                assert broad_summary["denominator_jobs"] == len(broad_jobs)
                write_json(output / "broad_summary.json", broad_summary)
                base = {"terms": ["RAG"], "fields": ["description"], "sections": ["responsibilities", "requirements"],
                        "aliases": {"RAG": ["GraphRAG", "RAGFlow"]}, "match_mode": "ascii_token",
                        "filters": {"include_closed": True}, "page_size": 100}
                first = await call("query_job_catalog", base)
                catalog = first
                listed = []
                while True:
                    listed += catalog["results"]
                    if not catalog["has_more"]:
                        break
                    catalog = await call("query_job_catalog", {**base, "offset": catalog["next_offset"], "snapshot_id": first["snapshot_id"]})
                assert len(listed) == len({j["key"] for j in listed}) == first["matched_jobs"]
                summary_args = {k: v for k, v in base.items() if k not in {"fields", "page_size"}}
                summary_args.update(corpus_id=first["corpus_id"], evidence_samples_per_technology=1)
                summary = await call("summarize_job_technical_mentions", summary_args)
                assert summary["denominator_jobs"] == first["matched_jobs"]
                details = []
                page_args = {**summary_args, "evidence_samples_per_technology": 0, "include_details": True,
                             "page_size": 100, "snapshot_id": summary["snapshot_id"]}
                page = await call("summarize_job_technical_mentions", page_args)
                while True:
                    details += page["details"]
                    if not page["has_more"]:
                        break
                    page = await call("summarize_job_technical_mentions", {**page_args, "offset": page["next_offset"]})
                assert len(details) == len({j["key"] for j in details}) == summary["denominator_jobs"]
                evidence_count = 0
                by_category = defaultdict(set)
                raw_by_key = {}
                full_jobs = []
                # All original-source evidence is checked against full text fetched
                # through the NEW MCP, not against the fixture file or database.
                for start in range(0, len(broad_jobs), 20):
                    refs = [{"job_id": j["job_id"], "source": j["source"], "version": j["version"]} for j in broad_jobs[start:start + 20]]
                    batch = await call("get_jobs_batch", {"jobs": refs, "corpus_id": first["corpus_id"]})
                    assert not batch["errors"]
                    full_jobs.extend(batch["results"])
                    for job in batch["results"]:
                        raw_by_key[job["key"]] = job["raw"]["description"]
                        assert not job["source_text_truncated"]
                        for section in job["sections"]:
                            assert raw_by_key[job["key"]][section["source_start"]:section["source_end"]] == section["text"]
                write_json(output / "full_jobs.json", full_jobs)
                for job in details:
                    for evidence in job["technical_mentions"] + job["match_evidence"]:
                        raw = raw_by_key[job["key"]]
                        assert raw[evidence["source_start"]:evidence["source_end"]] == evidence["text"]
                        assert raw[evidence["match_start"]:evidence["match_end"]] == evidence["matched_text"]
                        assert not evidence["verified"]
                        evidence_count += 1
                    for evidence in job["technical_mentions"]:
                        by_category[evidence["technology"]].add(job["key"])
                for category in summary["categories"]:
                    assert len(by_category[category["technology"]]) == category["job_count"]
                # Complete unresolved section enumeration, not just the first sample.
                unknown_args = {**base, "sections": ["unknown"]}
                unknown_first = await call("query_job_catalog", unknown_args)
                unknown_page, unknown_jobs = unknown_first, []
                while True:
                    unknown_jobs += unknown_page["results"]
                    if not unknown_page["has_more"]:
                        break
                    unknown_page = await call("query_job_catalog", {**unknown_args, "offset": unknown_page["next_offset"],
                                                                     "snapshot_id": unknown_first["snapshot_id"]})
                assert len(unknown_jobs) == first["unknown_match_jobs"]
                excluded_keys = {j["key"] for j in listed}
                unresolved = [j for j in unknown_jobs if j["key"] not in excluded_keys]
                assert len(unresolved) == first["unresolved_jobs"]
                _, preferred_jobs = await enumerate_catalog({**base, "sections": ["preferred"]})
                preferred_only = [j for j in preferred_jobs if j["key"] not in excluded_keys]
                assert len(preferred_only) == first["preferred_only_match_jobs"]
                write_json(output / "preferred_only.json", preferred_only)
                write_json(output / "catalog_jobs.json", listed)
                # Exercise original search path, with exact hard filters and all
                # paid services disabled in the fixture. Explicit rerank is honest.
                candidates = await call("search_job_candidates", {"query": "企业RAG知识库建设", "city": "广州", "min_salary": 20000,
                                          "reformulations": ["文档解析 向量检索 重排序"], "candidate_limit": 5, "rerank": True})
                assert candidates["rerank"]["reason"] == "not_configured"
                for job in candidates["results"]:
                    assert job["normalized"]["city"] == "广州" and job["normalized"]["salary_min"] >= 20000
                    assert len(job["evidence"]) == len(job["evidence_chunk_ids"]) == len(job["evidence_details"])
                if candidates["results"]:
                    job = candidates["results"][0]
                    verified = await call("get_job", {"job_id": job["job_id"], "source": job["source"]})
                    assert verified["version"] == job["version"] and verified["job_status"] == job["job_status"]
                # Final optimistic snapshot guard is another MCP tool call.
                await call("query_job_catalog", {**base, "count_only": True, "snapshot_id": first["snapshot_id"]})
                report = {"status": "PASS", "question": "统计岗位职责或者任职要求出现RAG的岗位中，相关的技术要求是什么",
                    "source_transport": "supplied_csv_import", "source_corpus_id": first["corpus_id"],
                    "acceptance_transport": "real_streamable_http_mcp", "isolated": True,
                    "source_tool_calls": 0, "acceptance_tool_calls": len(trace),
                    "tool_call_counts": dict(Counter(t["tool"] for t in trace)), "tools": sorted(names),
                    "matched_jobs_under_rules": first["matched_jobs"], "unresolved_jobs": len(unresolved),
                    "preferred_only_match_jobs": first["preferred_only_match_jobs"],
                    "evidence_spans_checked": evidence_count, "paid_model_calls": 0,
                    "semantic_count_complete": False, "all_literal_rows_processed": True,
                    "note": "PASS means MCP transport, source spans, pagination, and rule counts verified; not exhaustive semantic judgment.",
                    "completed_at": datetime.now(timezone.utc).isoformat()}
                for filename, value in [("acceptance.json", report), ("trace.json", trace), ("catalog.json", first),
                                        ("summary.json", summary), ("details.json", details), ("unresolved.json", unresolved),
                                        ("candidates.json", candidates)]:
                    write_json(output / filename, value)
                print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        api.should_exit = mcp.should_exit = True
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.to_thread(api_thread.join, 5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "jobs-20261023.csv")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "calls").mkdir()
    import hashlib
    import subprocess
    implementation_paths = sorted(Path("job_rag").rglob("*.py")) + [Path(__file__)]
    write_json(args.output / "manifest.json", {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "csv_path": str(args.csv.resolve()), "csv_sha256": hashlib.sha256(args.csv.read_bytes()).hexdigest(),
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "implementation_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in implementation_paths},
        "baseline_used_for_extraction": False,
        "report_generation": "Codex synthesizes recorded MCP results; no configured Job-RAG chat model",
        "paid_model_calls": 0})
    for name in ("httpx", "mcp", "mcp.server", "mcp.server.streamable_http", "mcp.server.streamable_http_manager"):
        logging.getLogger(name).setLevel(logging.WARNING)
    settings = prepare_csv(args.csv, args.output)
    asyncio.run(acceptance(args.output, settings))


if __name__ == "__main__":
    main()
