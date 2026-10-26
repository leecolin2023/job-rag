# Job-RAG 源码怎样协作？——沿两次不同的业务操作读完整项目

如果只依照文件名阅读，项目看起来是十个目录的集合：预处理、存储、分块、索引、检索、查询、接口、模型、实验等。更有用的方法是追踪两件真正发生的事：**有一条岗位更新了**，以及**用户提出一次复杂的招聘问题**。这两条链路的状态变化解释了模块为什么必须分开。

## 一、当一条 JD 从“Python 必备”改成“vLLM 部署必备”

外部采集流程交来新的 CSV，`preprocessing` 先整批校验、将薪资和城市等文本转换为可比较的属性，再通过 `source:job_id` 找到原职位并新增版本。这时数据库已经保存了新 JD，但旧分块还可能存在：**不能因为岗位更新成功，就立即用旧索引代表新岗位**。

因此 `storage` 持有当前文本、历史版本和索引任务；`indexing` 异步于导入事务执行一次性 Worker，调用 `chunking` 将新的 JD 按章节、条目、条件语境拆成可溯源块，然后可选借助 `providers` 的 Embedding 接口生成向量。全部块准备好以后才原子替换，并标记索引版本就绪。

~~~text
外部 data/jobs.csv → preprocessing（校验、规则派生、版本）
                                     ↓
                            storage（现行 JD、历史、任务）
                                     ↓
                      indexing（处理任务、检查版本）
                                     ↓
                  chunking（有章节/条目的证据块）
                                     ↓
                   providers（可选向量编码）
                                     ↓
                     storage（原子写入 chunks）
~~~

[数据输入](../data/README.md)、[预处理](preprocessing/README.md)、[存储](storage/README.md)、[分块](chunking/README.md)、[索引](indexing/README.md)和[模型客户端](providers/README.md)各自解释这里的设计取舍。

## 二、当用户问“广州有哪些适合我的 RAG 岗位？”

这个问题既要排除城市、薪资不符合的岗位，又要在剩下的 JD 中找到工作内容相关者。`interfaces` 让网页、CLI 或 OpenCode Agent 调用相同业务逻辑；`retrieval` 先过滤硬条件，再由 BM25、可选向量与 RRF 产生有排名的候选，返回来源与可核查的原文片段。DeepSeek Agent 还可以通过 MCP 获取完整 JD，对比“必备、优先、否定、例外”等要求。

但如果问题变成“广州到底多少份 JD **字面提到** vLLM”，上一条有 Top-K 截断的搜索链路就不再正确。`querying` 不通过 BM25/Embedding，直接在明确的数据范围里完成字面扫描、计数和一致性分页。二者是不同工具，不能用“搜索命中数量”冒充“全库数量”。

~~~text
网页 / CLI / OpenCode Agent
           ↓
       interfaces
       ├── retrieval → 候选召回、证据、可选生成
       └── querying  → 全库字面计数、分页、原文批量读取
                           ↓
                        storage
~~~

继续阅读[候选检索](retrieval/README.md)、[确定性查询](querying/README.md)、[对外接口](interfaces/README.md)可看到两条路径为什么并存。

## 三、为什么还有一套独立的 experiments？

增加章节分块或 Embedding 后，搜索“看起来更聪明”并不能证明效果改进。数据、文本表示、查询和人工标注任何一项变化，都可能改变排名。`experiments` 因此冻结原始数据和评测问题，分别比较召回与重排；其缓存和结果不自动替换线上索引。阅读[实验机制](experiments/README.md)及[实验使用](../experiments/README.md)。

## 四、怎样在代码中顺着调用看？

不必把下面当作需要背诵的模块目录。它们是上述状态变化对应的实际入口：

- **岗位更新**：`preprocessing/importer.py` → `indexing/tasks.py` → `indexing/worker.py` → `storage/database.py`。
- **候选查找**：`interfaces/api.py` → `retrieval/search.py` → `retrieval/candidates.py` → `retrieval/answer.py`。
- **字面统计**：`interfaces/mcp_server.py` → `querying/catalog.py` → `storage/serialization.py`。
- **模型调用**：`providers/client.py`（在线）与 `experiments/bailian.py`（离线实验）互相独立。

顶层 `config.py` 生成包含模型与分块条件的索引签名，帮助保证新旧版本不混用。当前 Python 命令在 `pyproject.toml` 中指定为 `job-rag`、`job-rag-mcp`、`job-rag-experiment`。改动代码位置后需重新安装或重建镜像；目录重组不会自动改变既有数据库、生产索引或服务器运行状态。

项目目前的核心仍是**可靠保存招聘原文，提供可追溯检索和全库字面访问**；还未形成完整的技能/工作任务/能力深度语义事实表。理解这一点，才能知道下一步改进应该落在检索、业务语义抽取，还是运行可靠性，而不是机械地继续增加组件。