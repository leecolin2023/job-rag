"""Read-only MCP server assembly; tools live in individual mcp_tools modules."""
import os
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from .mcp_instructions import INSTRUCTIONS
from .mcp_transport import api_request
from .mcp_tools import register_tools


def create_mcp(api_url=None):
    api_url = (api_url or os.getenv("JOB_RAG_API_URL", "http://127.0.0.1:8008")).rstrip("/")
    server = FastMCP("jobrag", instructions=INSTRUCTIONS,
        host=os.getenv("MCP_HOST", "127.0.0.1"), port=int(os.getenv("MCP_PORT", "8001")),
        stateless_http=True, json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
            allowed_hosts=["127.0.0.1:*", "localhost:*", "mcp:*", "testserver"],
            allowed_origins=["http://127.0.0.1:*", "http://localhost:*"]))
    register_tools(server, api_request(api_url))

    @server.custom_route("/health", methods=["GET"])
    async def health(_: Request):
        return JSONResponse({"status": "ok", "service": "jobrag-mcp"})
    return server


def main():
    create_mcp().run(transport="streamable-http")


if __name__ == "__main__":
    main()
