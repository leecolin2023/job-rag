"""MCP tool: get_jobs_batch."""
from ...querying.get_jobs_batch import BatchRequest, JobRef


def register(server, request):
    @server.tool()
    def get_jobs_batch(jobs: list[JobRef], corpus_id: str | None = None,
                       sections: list[str] | None = None, include_raw: bool = True) -> dict:
        """一次读取1—20份完整JD。jobs含job_id、source(默认boss)、可选version。

        返回逐项not_found/version_changed错误；corpus_id可绑定枚举的数据版本。
        不会隐藏关闭岗位，必须结合状态判断；最终推荐前复核最新全文。
        sections按需选章节；include_raw默认保留完整原文。章节位置对应原始description，
        section_coverage说明未识别正文，condition是规则标签而非核验事实。
        """
        payload = BatchRequest(jobs=jobs, corpus_id=corpus_id, sections=sections, include_raw=include_raw)
        return request("POST", "/api/jobs/batch", json=payload.model_dump())
