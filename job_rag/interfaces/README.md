# 服务接口：怎样把岗位能力交给网页、脚本和 Agent？

数据库里的岗位、BM25 排名和原文统计本身只是 Python 函数。真实使用时，浏览器要发送 HTTP 请求，命令行要解析参数，Agent 则需要知道有哪些安全可调用的工具。`interfaces/` 把这些外部形式转换为同一套内部业务调用；它不复制检索算法，也不替模型判断某岗位是否适合。

## 一、从一次用户提问看调用链

~~~text
网页 → FastAPI /api/search ──→ retrieval.answer → 证据列表/可选 Chat
Agent → MCP 工具 → HTTP API ──→ retrieval / querying → 数据库
CLI → 命令解析 ──────────────→ preprocessing / indexing / retrieval / storage
~~~

`api.py` 负责 HTTP 参数解析、业务函数调用、数据库连接生命周期和状态码映射；`mcp_server.py` 用 FastMCP 把有限业务接口包装为工具，调用后端 API；`cli.py` 为人工导入、重建索引、启动服务和查询提供入口。`static/index.html` 是随 Python 包发布的简单网页，通过 `/api/search` 和岗位详情 API 读取结果，并非一套独立的前端服务器。

## 二、为什么 MCP 不提供任意数据库访问？

Agent 擅长选择工具和阅读证据，却可能受误解或恶意文本影响。如果允许它运行任意 SQL 或修改岗位状态，一个普通求职问题就可能误触写操作。因此 MCP 只暴露五个**只读**工具：

| 工具 | 使用时机 |
|---|---|
| `get_knowledge_base_stats` | 了解数据规模和检索状态 |
| `search_job_candidates` | 寻找语义相关、可能满足条件的候选 |
| `query_job_catalog` | 全库字面查找、准确字面计数、分页 |
| `get_jobs_batch` | 一次读取最多 20 份指定 JD |
| `get_job` | 核对一个岗位的完整正文、状态和版本 |

“广州多少个岗位提到了 vLLM”应走 catalog；“哪个岗位更适合做模型服务”通常先召回候选再阅读全文；明确指定两条 JD 则可以直接批量读取。当前这些选择主要由 OpenCode Agent 提示策略完成，不是后端强制的任务路由引擎。

## 三、哪些 HTTP 路由实际承担工作？

`GET /api/stats` 返回语料与索引统计；`POST /api/search` 返回普通检索及可选生成；`POST /api/candidates` 返回多查询候选；`POST /api/catalog` 和 `POST /api/jobs/batch` 支持全库字面分析与批量全文；`GET /api/jobs/{job_id}` 返回指定 JD。

另有 `POST /api/import` 与 `POST /api/jobs/{job_id}/status` 两个管理接口，需启用 `ADMIN_TOKEN` 并携带 Bearer 令牌。CSV 上传有限额，任务失败或快照变化会映射为适当 HTTP 错误，例如持续分页期间数据变化返回 409。管理接口**不映射**为 MCP 工具。

## 四、怎样运行？服务安全边界在哪里？

~~~bash
pip install -e '.[test]'
job-rag serve --host 127.0.0.1 --port 8000
# 在另一终端启动 MCP（后端地址由 JOB_RAG_API_URL 配置）
job-rag-mcp

# 直接使用 ASGI 时的当前模块入口
uvicorn job_rag.interfaces.api:app --host 127.0.0.1 --port 8000
~~~

重新组织目录后应重新安装包，使 `pyproject.toml` 的脚本入口更新。Docker 镜像也必须重建才会使用新的代码位置；移动文件并不等于已经重启远端服务。

本机回环 API/MCP 与公网访问的信任边界不同。生产式公网访问应经 HTTPS、鉴权和限流网关，不应把内部裸端口直接映射到互联网。MCP 接收的岗位原文是不可信数据，不能当指令执行；来源编号存在也不足以保证模型结论正确。更多部署细节见[根 README](../../README.md)与[公网接入](../../docs/remote-access.md)。