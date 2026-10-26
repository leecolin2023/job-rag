# 为什么需要 API、MCP、CLI 三个入口，而不让 Agent 直接访问数据库？

系统内部已经有 Python 函数可以导入、检索、统计岗位。问题是不同用户的操作习惯不同：浏览器需要 HTTP，运维需要命令行，DeepSeek Agent 需要知道可以调用哪些具备明确参数和结果格式的工具。

如果为了方便而让 Agent 直接执行 SQL，普通“找工作”的请求就可能接触修改状态、删除数据等权力；若每个入口都重新写一遍检索逻辑，则同样的筛选条件可能在网页和 Agent 中得到不同结果。`interfaces/` 因此负责**安全地暴露同一套业务能力，不重复实现业务本身**。

## 一、一次网页搜索怎样到达数据库？

用户在网页输入“广州 RAG 20K”，`static/index.html` 通过 `POST /api/search` 把查询和显式筛选条件交给 FastAPI。`api.py` 负责校验参数及生命周期，调用 `retrieval.answer.answer()`，后者再访问结构条件、分块与模型接口。API 将结果、来源和警告返回给页面。

网页并不会因为系统里有 MCP 就自动获得 DeepSeek 的理解能力；网页可选 Chat 是另一条生成链路。`api.py` 本身不计算 BM25，也不做全库计数，这可以避免同一算法在几个入口出现不同版本。

## 二、一次 Agent 查询为什么要经过 MCP？

OpenCode 的 DeepSeek Agent 不能仅靠“模型知道 Python 函数名”来执行操作，需要受协议约束的工具目录和输入参数。`mcp_server.py` 使用 FastMCP 暴露只读工具，再转换成后端 HTTP 调用。

例如“广州多少条 JD 提到 vLLM？”应该调用 `query_job_catalog`；“找适合我的 RAG 职位”应调用 `search_job_candidates`；“比较这两份确定的岗位”直接调用 `get_jobs_batch`。若让全部问题强制进入多查询 RRF，精确字面统计就会被 Top-K 截断误导。

MCP 当前只提供五个只读工具：`get_knowledge_base_stats`、`search_job_candidates`、`query_job_catalog`、`get_jobs_batch`、`get_job`。不提供导入、改状态或任意 SQL，这限制了 Agent 和招聘文本中潜在恶意指令造成的破坏范围。

## 三、管理权限为什么与读取权限分开？

`POST /api/import` 和 `POST /api/jobs/{job_id}/status` 会改变数据，必须在配置 `ADMIN_TOKEN` 后使用 Bearer 认证；网页和 MCP 不暴露管理员凭据。原始 API/MCP 在本地回环地址运行时不等于可以安全公开到网络；远程入口需经过 HTTPS、认证、限流及请求大小约束。

`cli.py` 则提供人工控制的 `job-rag import / worker / reindex / status / serve` 等命令。把危险操作保留在受控 CLI 或管理 API 中，而不是把所有操作授予查询 Agent，是权限最小化的工程选择。

## 四、为什么有时工具返回“数据变化，重新开始”？

`query_job_catalog` 逐页查看全部岗位时，如果另一进程更新了数据，继续拼接旧第一页和新第二页就可能重算或漏算。查询层通过指纹发现变化时抛出冲突，`api.py` 映射为 HTTP 409，MCP 将其转为“从头重新枚举”的错误提示。接口层并不试图替业务偷偷续跑一个失效快照。

同理，当模型调用期间职位状态改变，最终能否继续返回推荐由回答模块复核，而不是网关替它判断。

## 五、如何启动以及当前不能保证什么？

~~~bash
pip install -e '.[test]'
job-rag serve --host 127.0.0.1 --port 8000
# 另一个进程：
job-rag-mcp
# 或直接以 ASGI 启动：
uvicorn job_rag.interfaces.api:app --host 127.0.0.1 --port 8000
~~~

`pyproject.toml` 的入口指向 `interfaces/cli.py` 与 `interfaces/mcp_server.py`；模块移动后应重新安装或重建镜像。完整公网配置见[远程访问](../../docs/remote-access.md)。

任务路由目前主要是 Agent 的提示策略，不是后端强制状态机；管理接口不等于多租户权限系统；访问 MCP 不等于所用模型一定正确理解了证据。接口层保证的是**清楚的调用边界和权限边界**，不是最终业务判断的真实性。