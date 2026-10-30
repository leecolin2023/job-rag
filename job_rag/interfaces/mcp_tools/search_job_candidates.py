"""MCP tool: search_job_candidates."""


def register(server, request):
    @server.tool()
    def search_job_candidates(
        query: str,
        reformulations: list[str] | None = None,
        city: str | None = None,
        district: str | None = None,
        min_salary: float | None = None,
        max_salary: float | None = None,
        salary_period: str = "month",
        salary_mode: str = "lower_bound",
        experience_years: float | None = None,
        education: str | None = None,
        skills: list[str] | None = None,
        active_only: bool = False,
        include_closed: bool = False,
        candidate_limit: int = 20,
        rerank: bool = False,
    ) -> dict:
        """多查询候选召回：传原问题、最多4条同义改写及用户明确硬条件。

        返回证据而非最终语义结论，由调用模型阅读并排序。salary_mode 为 lower_bound
        （薪资下限达标）或 overlap（区间覆盖）；skills 每项必须字面出现。
        unknown 不代表在招；include_closed 仅用于用户明确要求的历史分析。
        rerank默认false；显式true且服务已配置时才调用可能计费的重排模型。
        重排使用完整JD、最多60个候选；失败保留融合顺序并返回原因，不伪称已重排。
        """
        from ...retrieval.candidates import CandidateRequest
        payload = CandidateRequest(query=query, reformulations=reformulations or [], city=city,
                                   district=district, min_salary=min_salary, max_salary=max_salary,
                                   salary_period=salary_period, salary_mode=salary_mode,
                                   experience_years=experience_years, education=education,
                                   skills=skills or [], active_only=active_only, include_closed=include_closed,
                                   candidate_limit=candidate_limit, rerank=rerank)
        return request("POST", "/api/candidates", json=payload.model_dump())
