"""MCP tool: get_knowledge_base_stats."""


def register(server, request):
    @server.tool()
    def get_knowledge_base_stats() -> dict:
        """查看知识库规模、城市、招聘状态及索引就绪情况。"""
        return request("GET", "/api/stats")
