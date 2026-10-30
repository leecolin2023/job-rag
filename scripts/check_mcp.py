"""Read-only MCP HTTP smoke check against the running Docker services."""
import asyncio
import json
import os
from pathlib import Path
import ssl

import httpx

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main():
    url = os.getenv("JOB_RAG_MCP_URL", "http://127.0.0.1:8009/mcp")
    headers = {}
    if os.getenv("JOB_RAG_TOKEN_FILE"):
        headers["Authorization"] = "Bearer " + Path(os.environ["JOB_RAG_TOKEN_FILE"]).read_text().strip()
    context = ssl.create_default_context(cafile=os.getenv("JOB_RAG_CA_FILE"))

    def client_factory(**kwargs):
        return httpx.AsyncClient(**kwargs, verify=context, trust_env=False)

    async with streamablehttp_client(url, headers=headers, httpx_client_factory=client_factory) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            catalog = await session.list_tools()
            names = {tool.name for tool in catalog.tools}
            assert names == {"get_knowledge_base_stats", "search_job_candidates", "get_job",
                             "query_job_catalog", "get_jobs_batch", "summarize_job_technical_mentions"}
            stats = await session.call_tool("get_knowledge_base_stats", {})
            assert not stats.isError
            result = await session.call_tool("search_job_candidates", {
                "query": "广州 企业知识库问答", "city": "广州", "min_salary": 20000,
                "reformulations": ["RAG 检索增强生成", "知识库 向量检索"], "candidate_limit": 3,
            })
            assert not result.isError, result
            data = result.structuredContent or json.loads(result.content[0].text)
            assert data["results"]
            first = data["results"][0]
            assert first["normalized"]["city"] == "广州"
            assert first["normalized"]["salary_min"] >= 20000
            detail = await session.call_tool("get_job", {"job_id": first["job_id"], "source": first["source"]})
            assert not detail.isError
            full_catalog = await session.call_tool("query_job_catalog", {"count_only": True})
            assert not full_catalog.isError
            full_data = full_catalog.structuredContent or json.loads(full_catalog.content[0].text)
            assert full_data["count_complete"] and full_data["count_kind"] == "exact_literal_not_semantic"
            batch = await session.call_tool("get_jobs_batch", {
                "jobs": [{"job_id": first["job_id"], "source": first["source"], "version": first["version"]}],
            })
            assert not batch.isError
            print(json.dumps({"status": "PASS", "tools": sorted(names), "candidate_mode": data["mode"],
                              "semantic_assessment": data["semantic_assessment"], "first_title": first["title"]}, ensure_ascii=False))


asyncio.run(main())
