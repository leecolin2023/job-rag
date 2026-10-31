# Job-RAG 离线实验：统一目录与命令

实验定义、评测数据和实验执行程序均在根目录 `experiments/`，生产包 `job_rag/` 只保留业务与检索等核心实现。实验程序可以调用生产核心模块，但生产模块不依赖实验代码。

**唯一命令：`job-rag-experiment`**。保留原有检索排名子命令 `prepare / recall / pool / rescore / rerank / report / audit-rerank-inputs / probe`，任务驱动实验通过同一入口调用 `run / prepare-review / evaluate`。取消 `job-rag-task` 入口。

- 通用实验代码：`experiments/cli.py`、`runner.py`、`bailian.py`、`metrics.py`；RAG 技术要求任务的专用执行/评分/抽样代码：`rag_tech_requirements/task_runner.py`、`task_eval.py`、`task_review.py`。
- 实验资料：`benchmark.v1.json`、`rag_tech_requirements/fixtures.json` 和 `gold.jsonl`。
- 执行产物：`runtime/experiments/`（Git 忽略，不能作为产品事实或已核验标签）。
- [实现细节](IMPLEMENTATION.md)｜[RAG 技术要求统计实验](rag_tech_requirements/README.md)

新命令示例：

~~~bash
pip install -e '.[test,experiments]'

job-rag-experiment run \
  --dataset experiments/rag_tech_requirements/fixtures.json \
  --gold experiments/rag_tech_requirements/gold.jsonl \
  --output runtime/experiments/rag-task-demo
~~~

## 历史检索排名实验说明

### 怎样设计一场能说明问题的 Job-RAG 检索实验？

用户真正关心的是“能不能找到符合自己意图的岗位”，而不是“某个预设岗位在排行榜上的位置”。如果检索评测只用从一份 JD 反推的搜索问题，再把这条 JD 当作唯一正解，BM25 可能因为词汇重复而有明显优势；Embedding 如果找出另一份同样合适的 JD，反而可能被评为失败。

因此本目录的 `benchmark.v1.json` 不是标准答案大全，而是首轮**种子标注基准**：30 条查询、15 个主题组、14 条 dev 和 16 条 test。它适合观察已知正例的排名，却不足以直接代表全部真实用户查询的相关性。

## 一、为什么不能同时优化召回和 Rerank？

假设改变分块后新方案从 Top-50 找到更多岗位，又同时启用 Reranker；最后 Top-5 改善，我们不知道是候选增加还是排序变聪明。所以实验分成两步：

~~~text
固定问题、硬条件、Embedding 模型与语料
  → 对比分块 A/B/C/D/E 与 BM25 参考 → 冻结岗位级候选
  → 合并候选并人工复核
  → 固定同一候选、同一文档表示 → 对比不同重排方法
~~~

第一轮回答“找得到吗”，第二轮回答“同样的候选谁排前面”。Reranker 不能找回完全不在候选池中的岗位。

## 二、先运行不付费的准备，再决定是否付费

~~~bash
pip install -e '.[test,experiments]'

# 仅冻结数据、查询、策略和实现哈希
job-rag-experiment prepare --output runtime/experiments/prepared-v1

# 在本机交互准备独立百炼配置，密钥不要放在命令中
python3 scripts/setup_bailian_env.py --host https://你的业务空间.cn-beijing.maas.aliyuncs.com

# 小探针验证模型/网络/权限（真实付费请求）
job-rag-experiment --max-requests 2 probe --execute
~~~

随后执行第一轮召回，并生成报告：

~~~bash
job-rag-experiment recall --prepared runtime/experiments/prepared-v1 \
  --output runtime/experiments/recall-v1 --candidate-limit 50 --execute
job-rag-experiment report runtime/experiments/recall-v1
~~~

为什么不在看到这份报告时就选赢家？因为许多未标注岗位可能同样满足原问题。接下来应将各方案候选汇集，依据原文逐条判断：

~~~bash
job-rag-experiment pool --recall-run runtime/experiments/recall-v1 \
  --depth 50 --output runtime/experiments/review-v1.json

# 人工补齐证据、相关性等级和 reviewed 标记后，免重新调用 Embedding
job-rag-experiment rescore --recall-run runtime/experiments/recall-v1 \
  --judgments runtime/experiments/review-v1.json \
  --output runtime/experiments/recall-reviewed-v1
~~~

第二轮使用在 dev 中选定的召回方案，保持候选集合冻结。以下 D 只是命令示意，**不代表它已被证明最好**：

重排前可先检查完整 JD 请求体积，不需要模型配置或付费：

~~~bash
job-rag-experiment audit-rerank-inputs --recall-run runtime/experiments/recall-v1
~~~

重排已取消 1800 字节截断，统一使用完整原文。默认通过 UTF-8 字节加保留量进行保守预检，不能当作实际 Token 计数。可在审计时传 `--tokenizer-path`、运行时设置 `BAILIAN_RERANK_TOKENIZER_PATH` 使用同一份本地 tokenizer JSON，但须自行核实它适用于托管模型；加载文件本身不证明一致。未通过预检会在发送请求前停止。详见 [输入审计说明](../docs/rerank-input-audit-2026-10-28.md)。

~~~bash
job-rag-experiment rerank --recall-run runtime/experiments/recall-v1 \
  --arm D_section_typed_1100 --judgments runtime/experiments/review-v1.json \
  --output runtime/experiments/rerank-v1 --execute
job-rag-experiment report runtime/experiments/rerank-v1
~~~

尚无审阅标签时的 `--allow-provisional` 仅可用于管线调试，不能包装为经过人工复核的性能结论。

## 三、怎么看待目前结果？

首轮真实 Embedding 已经运行，章节切分在部分查询中提高种子岗位排名、部分查询中退化，BM25 对明确技术名词表现很强。**这不支持“一定应该换 Embedding”或“Embedding 总是不如 BM25”**，因为种子标注与输入表示存在限制。完整 Rerank 第二轮尚未执行。

快照、模型缓存、请求日志、候选审阅及报表均在 `runtime/experiments/`，被 Git 忽略，**不会自动修改线上索引**。模型调用需要 `--execute`，软件费用限制也不等于平台账单硬限额。要理解实验代码如何控制变量，请看[实现模块](IMPLEMENTATION.md)；要看实际数据与解释，请看[实验报告](../docs/recall-pilot-2026-10-25.md)和[逐题复核](../docs/recall-case-audit-2026-10-25.md)。
