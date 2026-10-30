"""HTTP transport shared by the individual MCP tool modules."""
import httpx
import time
import uuid


def api_request(api_url):
    def request(method, path, **kwargs):
        request_id = uuid.uuid4().hex
        started = time.monotonic()
        try:
            with httpx.Client(base_url=api_url, timeout=90, trust_env=False) as client:
                response = client.request(method, path, headers={"X-Request-ID": request_id}, **kwargs)
                if response.status_code == 409:
                    raise ValueError("数据或查询条件发生变化；请从第一页重新开始，不得混合旧结果。")
                response.raise_for_status()
                result = response.json()
                result["_trace"] = {"request_id": request_id, "transport": "mcp_to_api",
                                    "operation": path, "elapsed_ms": round((time.monotonic() - started) * 1000, 2)}
                return result
        except httpx.HTTPError:
            raise ValueError("岗位 API 不可用或请求无效；请检查服务健康状态与参数") from None
    return request
