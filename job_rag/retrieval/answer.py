"""Answer rendering/generation with citation checks and final source revalidation."""
import re

from ..providers.client import chat
from ..storage import Job
from .search import search


def answer(db, settings, request):
    result = search(db, settings, request)
    sources = result["results"]
    result["answer_mode"] = "extractive"
    if not sources:
        result["answer"] = "未找到满足条件的岗位。可放宽筛选条件；这不代表市场上不存在此类岗位。"
        return result
    labels = {"active": "已确认在招", "unknown": "未核验", "closed": "已关闭", "suspected_expired": "疑似失效"}
    lines = ["以下是候选岗位，请结合原招聘页面确认最新信息："]
    for i, item in enumerate(sources, 1):
        lines.append(f"[{i}] {item['title']}｜{item['company']}｜{item['salary']}｜{item['location']}；"
                     f"状态：{labels[item['job_status']]}，采集于 {item['collected_at']}。")
    result["answer"] = "\n".join(lines)
    if request.generate and settings.chat_api_key and settings.chat_model:
        try:
            generated = chat(settings, request.query, sources)
            citations = re.findall(r"\[(\d+)\]", generated)
            if not citations or any(not 1 <= int(citation) <= len(sources) for citation in citations):
                raise ValueError("Missing or invalid citations")
            result["answer"] = generated
            result["answer_mode"] = "llm"
        except Exception:
            result["warnings"].append("生成服务不可用，已返回可核对的岗位列表。")
    elif request.generate:
        result["warnings"].append("未配置生成模型，当前为来源列表，不是大模型生成回答。")
    # A model request can take seconds. Never return a source changed/closed during generation.
    with db.session() as session:
        for item in sources:
            current = session.get(Job, item["key"])
            if current is None or current.version != item["version"] or current.job_status != item["job_status"]:
                result["results"] = []
                result["total_matched"] = 0
                result["answer_mode"] = "extractive"
                result["answer"] = "岗位在检索期间发生更新，请重新查询以获取最新结果。"
                result["warnings"].append("已拦截过期结果。")
                break
    return result
