"""One registration module per read-only MCP tool."""

from . import get_knowledge_base_stats
from . import search_job_candidates
from . import get_job
from . import query_job_catalog
from . import get_jobs_batch
from . import summarize_job_technical_mentions

def register_tools(server, request):
    get_knowledge_base_stats.register(server, request)
    search_job_candidates.register(server, request)
    get_job.register(server, request)
    query_job_catalog.register(server, request)
    get_jobs_batch.register(server, request)
    summarize_job_technical_mentions.register(server, request)
