# Job-RAG 代码导读：从一条岗位到一次有证据的回答

这是 Python 业务代码目录，不是数据仓库或运行日志目录。读这些模块最有效的方法，不是记住每个文件名，而是跟随两条实际链路：**岗位如何变成可以搜索的资料**，以及**用户的问题如何变成可核对的结果**。

## 一、数据建设链路

~~~text
外部 CSV（../data/）
       ↓
preprocessing/  整份校验 → 城市/薪资等标准化 → 增量版本入库
       ↓
storage/        当前 JD + 历史版本 + 招聘状态 + 待索引任务
       ↓
indexing/       取任务 → chunking/ 章节与条目分块
       ↓
providers/      可选调用 Embedding
       ↓
storage/        原子替换当前版本 Chunk，标记索引就绪
~~~

这条链路把**记录是否保存成功**和**检索索引是否构建完成**分开。即使远端 Embedding 不可用，也应保留岗位原文与可重试任务；只有索引版本与当前岗位一致时，搜索才使用对应证据。

[原始数据](../data/README.md)解释来源与原文保存；[预处理](preprocessing/README.md)解释校验、规则标准化和增量导入；[存储](storage/README.md)解释五张表；[分块](chunking/README.md)解释章节与证据位置；[索引](indexing/README.md)解释任务和原子替换；[模型接入](providers/README.md)解释何时真的发生远端请求。

## 二、用户查询链路

~~~text
网页 / CLI / Agent
         ↓
interfaces/（HTTP、CLI 或只读 MCP）
         ├── querying/  完整字面计数、分页、完整 JD、确定性过滤
         └── retrieval/ 候选召回：BM25 + 可选向量 + RRF
                           ↓
                     证据/来源列表或可选模型解释
~~~

为什么分两条查询路径？“广州多少岗位字面提到 vLLM”需要全库扫描，不能用 Top-20 当总数；“找负责企业 RAG 工程的岗位”需要相关性排序，但相关性又不等于岗位真的把某技能作为必备条件。任务选择主要由外部 Agent 提示完成，当前不是后端强制路由状态机。

[服务接口](interfaces/README.md)解释三种入口及安全边界；[精确查询](querying/README.md)解释全库字面计数和一致性分页；[候选检索](retrieval/README.md)解释硬过滤、BM25、RRF、证据和可选 Chat；[离线实验](experiments/README.md)解释怎样判断变化来自召回还是排序。

## 三、从哪里开始读源代码？

如果想理解数据更新，按 `preprocessing/importer.py → indexing/tasks.py → indexing/worker.py → storage/database.py` 阅读。如果想理解用户查询，按 `interfaces/api.py → retrieval/search.py → retrieval/candidates.py → retrieval/answer.py` 阅读。统计任务则从 `interfaces/mcp_server.py → querying/catalog.py` 开始。

顶层 `config.py` 统一读取环境变量并计算索引签名；`__init__.py` 声明 Python 包。三种命令入口在 `pyproject.toml`：`job-rag`、`job-rag-mcp` 与 `job-rag-experiment`。文件重组后需要重新安装 Python 包或重建镜像，但**移动代码本身不迁移数据库、不重建索引、也不证明线上已切换**。

本项目当前核心是**可追溯的招聘检索与数据查询**。它并未将所有 JD 的技能、工作任务、能力深度与招聘约束完整抽成可复用的业务事实表；需要这种精确语义统计时，仍必须补上可靠的逐岗位判定和汇总工作。