# 服务接口与启动入口

本目录接收外部请求、校验参数与权限、调用业务模块，再返回结果。不实现检索算法，不自行判断岗位能力，不把管理写入能力暴露给 Agent。

| 文件/目录 | 职责 |
|---|---|
| `api.py` | FastAPI 生命周期、HTTP 路由、管理鉴权、请求大小限制和异常状态映射 |
| `mcp_server.py` | 五个只读 MCP 工具到 HTTP API 的适配，以及工具使用指导 |
| `cli.py` | 初始化、迁移、导入、索引、查询、状态管理和启动命令 |
| `static/index.html` | API 首页提供的网页，随包打包，不是独立前端服务 |

## HTTP 路由

| 接口 | 业务实现 |
|---|---|
| `GET /`、`GET /health` | 网页文件与数据库连通性检查 |
| `GET /api/stats` | `querying.jobs.knowledge_base_stats()` |
| `POST /api/search` | `retrieval.answer.answer()` |
| `POST /api/candidates` | `retrieval.candidates.candidates()` |
| `POST /api/catalog` | `querying.catalog.catalog_query()` |
| `POST /api/jobs/batch` | `querying.catalog.batch_jobs()` |
| `GET /api/jobs/{job_id}` | `querying.jobs.job_detail()`，包括版本与状态历史 |
| `POST /api/import` | `preprocessing.importer.import_csv()`，需要管理权限 |
| `POST /api/jobs/{job_id}/status` | `storage.status.set_status()`，需要管理权限 |

管理鉴权使用配置的 Bearer 令牌。MCP 仅提供 `get_knowledge_base_stats`、`search_job_candidates`、`query_job_catalog`、`get_jobs_batch`、`get_job`，没有导入、状态修改或任意 SQL 工具。

## 启动方式

重新安装项目以刷新命令入口后，常用命令保持不变：

```bash
pip install -e '.[test]'
job-rag serve --host 127.0.0.1 --port 8000
job-rag-mcp
```

直接 ASGI 启动：`uvicorn job_rag.interfaces.api:app --host 127.0.0.1 --port 8000`。
MCP 的后端地址由 `JOB_RAG_API_URL` 决定，监听地址与端口由 `MCP_HOST`、`MCP_PORT` 决定。Docker 仍调用相同控制台命令，重新构建后采用新入口；目录移动本身不会部署或重启现有容器。

`pyproject.toml` 将静态 HTML 绑定到 `job_rag.interfaces` 包，API 从自身目录读取文件，因此安装后不依赖仓库工作目录。旧顶层接口模块和静态资源目录不保留兼容副本。

路由策略由调用方 Agent 的提示完成，不是 MCP 的招聘理解能力；完整语义统计、恢复任务和跨调用硬预算仍未实现。边界见[任务路由说明](../../docs/task-routing.md)。
