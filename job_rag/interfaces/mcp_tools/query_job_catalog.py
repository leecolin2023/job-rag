"""MCP tool: query_job_catalog."""
from ...querying.catalog import CatalogRequest
from ...querying.filters import StructuredFilters


def register(server, request):
    @server.tool()
    def query_job_catalog(
        terms: list[str] | None = None,
        fields: list[str] | None = None,
        operator: str = "and",
        case_sensitive: bool = False,
        match_mode: str = "substring",
        filters: StructuredFilters | None = None,
        page_size: int = 20,
        offset: int = 0,
        snapshot_id: str | None = None,
        count_only: bool = False,
        sections: list[str] | None = None,
        aliases: dict[str, list[str]] | None = None,
        include_preferred: bool = False,
        evidence_limit: int = 8,
    ) -> dict:
        """全库字面查找/计数/分页枚举，不依赖索引。空terms枚举结构条件内全部岗位。

        fields仅title/description；operator为and/or；match_mode为substring/token/ascii_token。
        sections可限定responsibilities/requirements/preferred等章节；章节查询仅description。
        aliases是显式词表，如{"RAG":["GraphRAG","RAGFlow"]}，不自动扩词。
        返回原文证据、unknown_match_jobs及独立加分项数量；章节未识别不能当作不符合。
        字面出现不表示必备技能。返回matched_jobs为完整字面计数，不是语义统计。
        后续页传原条件、next_offset和snapshot_id；变化则中止重来。
        filters薪资单位元，经验是求职者年限可满足最低要求；unknown不代表在招。
        """
        payload = CatalogRequest(terms=terms or [], fields=fields if fields is not None else (["description"] if sections is not None else ["title", "description"]),
                                 operator=operator, case_sensitive=case_sensitive, match_mode=match_mode,
                                 filters=filters or StructuredFilters(), page_size=page_size, offset=offset,
                                 snapshot_id=snapshot_id, count_only=count_only, sections=sections,
                                 aliases=aliases or {}, include_preferred=include_preferred, evidence_limit=evidence_limit)
        return request("POST", "/api/catalog", json=payload.model_dump())
