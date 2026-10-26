# 检索评测：用同一批问题验证 Job-RAG 的改进

这里保存的是**实验输入**，不是线上索引，也不是模型已经得出的正确答案。`benchmark.v1.json` 包含 30 条查询，按 15 个主题组组织，每组两种问法；dev 14 条、test 16 条。很多问题最初只标注一条可在 CSV 中找到的种子岗位。因此当前可以观察“指定岗位是否进入前 K 名”，但不能自动宣称所有其他岗位都不相关。

## 一、为什么要分成两轮实验？

如果同时修改切块、Embedding、查询改写和 Reranker，最后效果变化就无法知道来自哪里。本项目先固定查询、硬条件和 Embedding 模型，比较**同一份 JD 怎样组织成检索文本**；再在固定候选集合上比较不同**排序方式**。

~~~text
第一轮：固定语料/问题 → 分块 A/B/C/D/E → Embedding 召回 → 岗位级排名
                    ↘ 同时保存 BM25 全文参考
                           ↓
                  合并候选、人工审阅
                           ↓
第二轮：选定同一候选集合 → 不重排/BM25/规则/Qwen Rerank → 排序指标
~~~

第一轮回答“某种文本表示是否更容易把相关岗位找出来”；第二轮回答“已找到的岗位能否排得更合理”。Reranker 不能救回根本没进候选池的岗位。

## 二、具体怎样执行？

先安装实验依赖。准备阶段只冻结数据、查询、分块和实现指纹，不调用付费模型。

~~~bash
pip install -e '.[test,experiments]'
job-rag-experiment prepare --output runtime/experiments/prepared-v1
~~~

百炼凭据在本地受限配置中准备，不将 Key 写入仓库或命令行。小探针、正式召回与第二轮重排会产生外部 API 请求，必须明确使用 `--execute`。

~~~bash
python3 scripts/setup_bailian_env.py --host https://你的业务空间.cn-beijing.maas.aliyuncs.com
job-rag-experiment --max-requests 2 probe --execute

job-rag-experiment recall --prepared runtime/experiments/prepared-v1 \
  --output runtime/experiments/recall-v1 --candidate-limit 50 --execute
job-rag-experiment report runtime/experiments/recall-v1
~~~

首先看候选和原文，不要只看平均排名。要让排名比较更接近真实求职体验，需把各系统的候选汇集并人工标注（0 不相关、1 部分相关、2 相关、3 直接匹配），正例记录对应原文依据。

~~~bash
job-rag-experiment pool --recall-run runtime/experiments/recall-v1 \
  --depth 50 --output runtime/experiments/review-v1.json

# 完成 reviewed 标注后，无须再调用 Embedding
job-rag-experiment rescore --recall-run runtime/experiments/recall-v1 \
  --judgments runtime/experiments/review-v1.json \
  --output runtime/experiments/recall-reviewed-v1
~~~

选定召回方案后才能做固定候选重排。下面的 D 是**命令示例**，不表示 D 已经在 dev 中胜出；若人工审阅未完成，可用 `--allow-provisional` 调试，但不能视为正式评价。

~~~bash
job-rag-experiment rerank --recall-run runtime/experiments/recall-v1 \
  --arm D_section_typed_1100 \
  --judgments runtime/experiments/review-v1.json \
  --output runtime/experiments/rerank-v1 --execute
job-rag-experiment report runtime/experiments/rerank-v1
~~~

## 三、实验结果应如何解读？

首轮真实 Embedding 已经运行，显示结构分块有时改善种子岗位排名，有时也会退化；BM25 对明确的技术词表现很强，但不能由此断言语义检索无价值。完整 Rerank 第二轮尚无实测胜负。

`runtime/experiments/` 存放缓存、冻结快照、请求日志、候选和报告，默认不提交 Git，也不会自动修改线上数据库。成本保护是本地软件估计而非供应商账单硬限额。进一步阅读[源码机制](../job_rag/experiments/README.md)、[实验协议](../docs/embedding-experiments.md)和[逐题案例](../docs/recall-case-audit-2026-10-25.md)。