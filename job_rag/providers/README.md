# 模型客户端：系统什么时候真正调用外部大模型？

Job-RAG 不把“安装 pgvector”“有 DeepSeek Agent”与“已经使用 Embedding”混为一谈。它包含两种不同的外部模型调用：一种将文本变成向量，帮助找相近内容；另一种阅读已找到的证据，帮助生成说明。`providers/client.py` 负责发送这两类 HTTP 请求，但不负责选择检索策略或判定岗位是否符合招聘条件。

## 一、Embedding 是怎样参与系统的？

构建索引时，[Worker](../indexing/README.md)把岗位 Chunk 传给 `embed(text_type="document")`；检索时，[search](../retrieval/README.md)把用户问题传给 `embed(text_type="query")`。两侧向量维度相同，系统才能计算余弦相似度，找到字面不同但语义相关的片段。

`client.py` 同时支持 OpenAI-compatible 的 `/embeddings` 和阿里百炼原生格式。在原生请求中通过 `text_type` 区分 query/document，模型、URL、密钥和维度从顶层 `Settings` 读取。

为了避免“返回了一个数组，所以就当作成功”的错误，客户端会校验返回向量的条数、顺序、维度及数值有效性。没配置模型密钥与模型名时，`embed()` 为每个输入返回 `None`，只使用关键词索引；配置后才会发送远程请求，可能产生费用。

## 二、Chat 为什么不能代替检索？

另一条路径是 `chat()`：当用户明确要求 `generate=true` 且配置了 Chat 模型，[回答模块](../retrieval/README.md)把问题、候选岗位、章节证据、采集时间与来源编号发到 Chat Completions。模型组织自然语言答案，但来源证据仍然来自数据库，不是模型凭空知道招聘详情。

Chat 可以解释“该岗位为何可能适合”，却不能单凭流畅文字保证正确。调用方还需要校验引用编号并复核岗位版本和招聘状态；即便编号存在，也不能自动证明每项结论忠于对应原文。

## 三、失败后发生什么？

`client.py` 负责网络请求和基本响应检查，不在内部悄悄决定业务降级。召回时 Embedding 失败，由检索层将结果降级为关键词；生成失败，由回答层返回来源列表；索引时 Embedding 失败，由 Worker 保留可重试的 `failed` 任务。相同网络故障在三个场景中有不同后果，职责划分因此更容易排查。

## 四、与 Agent 和离线 Rerank 的区别

OpenCode/DeepSeek 是 MCP 工具**调用方**，负责理解问题及阅读证据，不是 `client.py` 内置的 Embedding 模型。仓库里的 Qwen Rerank 适配、缓存、费用限制及实验日志属于独立的 `job_rag/experiments/bailian.py`，并没有通过本在线客户端自动接入线上 Rerank。

配置示例在[项目根 README](../../README.md)；不要把密钥写进仓库、日志或聊天。数据发送给第三方模型前，应了解所选服务的数据使用政策。