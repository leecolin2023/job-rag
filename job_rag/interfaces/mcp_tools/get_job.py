"""MCP tool: get_job."""


def register(server, request):
    @server.tool()
    def get_job(job_id: str, source: str = "boss", sections: list[str] | None = None,
                include_raw: bool = True) -> dict:
        """读取岗位全文、最新状态、版本及带原文位置的章节；最终推荐前必须复核。

        sections可选职责/任职要求等，include_raw默认true保留完整原文。
        条件标签为规则派生，不能当成必备技能核验事实。
        """
        from urllib.parse import quote
        params = {"source": source, "include_raw": include_raw}
        if sections is not None:
            params["sections"] = sections
        return request("GET", f"/api/jobs/{quote(job_id, safe='')}", params=params)
