# 在线模型服务接入

`client.py` 提供在线 Embedding 与 Chat HTTP 客户端，原平铺的模型接入模块不再保留。这里不是数据库 ORM，也不是 Agent、任务路由或重排序工作流。

| 函数 | 调用方 | 职责 |
|---|---|---|
| `embed()` | `indexing/worker.py`、`retrieval/search.py` | 分别生成文档向量与查询向量；支持 OpenAI-compatible 与 DashScope 格式，校验返回顺序、数量、维度及数值 |
| `chat()` | `retrieval/answer.py` | 将问题、来源编号、状态及证据提交 Chat Completions，返回模型文字 |

配置来自顶层 `config.py` 的 `Settings`，不在代码中写凭据。未启用 Embedding 时返回与输入等长的空向量标记；已配置时可能产生实际远端调用费用。

检索降级、任务重试、引用编号和版本复核由调用方负责，不由客户端悄悄执行另一套业务逻辑。引用编号合法不能保证生成结论忠实于证据。

离线百炼实验使用 `experiments/bailian.py`，包含独立缓存、费用保护和实验日志，不在本次目录重组中与在线客户端合并，也不因此启动完整 Rerank。
