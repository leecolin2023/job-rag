"""MCP tool: summarize_job_technical_mentions."""
from ...querying.filters import StructuredFilters
from ...querying.summarize_job_technical_mentions import TechnicalSummaryRequest


def register(server, request):
    @server.tool()
    def summarize_job_technical_mentions(
        terms: list[str] | None = None,
        aliases: dict[str, list[str]] | None = None,
        sections: list[str] | None = None,
        include_preferred: bool = False,
        technical_sections: list[str] | None = None,
        match_mode: str = "ascii_token",
        case_sensitive: bool = False,
        operator: str = "and",
        filters: StructuredFilters | None = None,
        technologies: list[str] | None = None,
        corpus_id: str | None = None,
        snapshot_id: str | None = None,
        include_details: bool = False,
        page_size: int = 20,
        offset: int = 0,
        evidence_samples_per_technology: int = 2,
    ) -> dict:
        """全库技术提及统计：默认RAG、职责/任职要求，显式aliases扩展GraphRAG或RAGFlow。

        按source+job_id去重，不是Top-K。返回词表、分母、条件分组及原文位置；
        必备/优先/否定/混合为规则标签，绝非核验事实。unknown_match_jobs与
        unresolved_jobs须报告，不能将未识别章节当成不符合。独立加分项默认单列。
        默认统计15类技术；technologies可指定返回中的类别ID。include_details支持
        完整逐岗位分页，后续传相同参数和snapshot_id；corpus_id绑定之前的目录。
        """
        payload = TechnicalSummaryRequest(
            terms=["RAG"] if terms is None else terms, aliases=aliases or {},
            sections=["responsibilities", "requirements"] if sections is None else sections,
            technical_sections=["responsibilities", "requirements"] if technical_sections is None else technical_sections,
            include_preferred=include_preferred, match_mode=match_mode, case_sensitive=case_sensitive,
            operator=operator, filters=filters or StructuredFilters(), technologies=technologies,
            corpus_id=corpus_id, snapshot_id=snapshot_id, include_details=include_details,
            page_size=page_size, offset=offset, evidence_samples_per_technology=evidence_samples_per_technology)
        return request("POST", "/api/technical-mentions", json=payload.model_dump())
