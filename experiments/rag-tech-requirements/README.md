# RAG 岗位技术要求统计：任务驱动 Experiments

## 唯一业务问题

> 统计岗位职责或者任职要求出现 RAG 的岗位中，相关的技术要求是什么？

旧的 30 条种子岗位检索题评测排名，并不能证明全库统计正确。新框架采用一道固定业务题，以及同一任务下的多种 JD 失败机制。旧 benchmark.v1.json 保留为历史检索实验。

## 任务口径

1. **筛选**：职责或任职要求出现独立 RAG 字面词，大小写不敏感；GraphRAG、RAGFlow 默认不自动算作独立 RAG。仅公司介绍或加分项提到 RAG，不纳入统计。
2. **否定**：「不要求 RAG」也属于字面出现，但绝不等于岗位要求该技能。统计范围与语义条件是两件事。
3. **技术**：逐项区分职责涉及、明确必备、优先、否定、任选、未明确；是否与 RAG 直接相关需单独审阅。
4. **计数**：同一岗位同一技术出现多次只计一个岗位。不同技术类别可以重叠，不允许相加作为总岗位数。
5. **未知章节**：单列待复核，不可默认为不符合。
6. **统计边界**：当前 CSV 是已采集的岗位集合，不是整个招聘市场，也不证明岗位正在招聘。

默认基线采用 **完整 JD 扫描 → 章节识别 → RAG 字面筛选 → 技术词证据 → 规则条件 → 去重聚合 → 模板报告**。它不需要 Top-K 检索，因此分块和检索阶段标记为 not_applicable。只有在另建检索实验臂时才启用相应阶段追踪。

## 数据和标准答案

- fixtures.json：16 条合成 JD；覆盖章节、GraphRAG/RAGFlow、否定、任选、条件混杂、去重、长文本、未知章节、加分项等边界。
- gold.jsonl：逐 JD 预期范围与技术要求，含逐条原文引用和条件标签。其 label_source 为 synthetic_spec；**这不代表真人核验过真实岗位**。
- 后续可针对 data/jobs.csv 创建单独的人工审阅 gold，只有人逐条核验后才能标注 label_source=human_reviewed。
- 对范围未决的记录使用 in_scope=null；只对确认完成全部技术标注的岗位使用 tech_review_complete=true。
- 任何部分标注的真实 JD 集合都只能评价已标注子集，不应称为全库准确率。

## 运行第一个实验

无需百炼、外部模型或连接生产数据库，不修改生产索引。

~~~bash
pip install -e '.[test]'

# 合成数据：基线+标准规格评测
job-rag-task run \
  --dataset experiments/rag-tech-requirements/fixtures.json \
  --gold experiments/rag-tech-requirements/gold.jsonl \
  --output runtime/experiments/rag-tech-fixture-01

# 真实岗位数据：全库字面/技术共现统计（没有语义核验）
job-rag-task run \
  --dataset data/jobs.csv \
  --output runtime/experiments/rag-tech-corpus-01

# 仅重新评分，不重新计算预测
job-rag-task evaluate \
  --run runtime/experiments/rag-tech-fixture-01 \
  --dataset experiments/rag-tech-requirements/fixtures.json \
  --gold experiments/rag-tech-requirements/gold.jsonl
~~~

### 从真实岗位生成待复核队列

~~~bash
job-rag-task prepare-review \
  --dataset data/jobs.csv \
  --limit 40 \
  --output runtime/experiments/rag-tech-review-01
~~~

生成 review_queue.jsonl 和 review_manifest.json。按独立 RAG 字面命中、未知章节、GraphRAG/RAGFlow 边界、其他章节出现 RAG、普通负例分层抽样；保存完整 JD 和基线建议供人工阅读。队列全部标记 pending_review，**不能直接当作 gold 输入评测**。确认每条范围与技术证据后，需要另行制作 gold.jsonl，使用 human_reviewed 标签并保留 description_sha256 以防源文本变更。

每次 output 必须是新的目录，不允许静默覆盖已有实验。

| 文件 | 含义 |
| --- | --- |
| manifest.json | 数据 SHA256、任务版本、技术词表和章节规则版本 |
| predictions.jsonl | 逐岗位筛选结果、技术证据、规则判断 |
| trace.jsonl | source / section / selection / evidence / interpretation / aggregation / answer 中间过程 |
| summary.json | 技术类别在命中岗位中的字面共现统计 |
| report.md | 带口径和限制说明的可读统计报告 |
| evaluation.json | 逐错误事实、首次可证实失败环节、评测指标（提供 gold 时） |
| evaluation.md | 人类可读的指标和失败类型报告（提供 gold 时） |

此阶段不把共现、规则派生条件或最终模板报告称为已验证的技术能力要求。

## 接入模型和 Agent 实验臂

当前交付了可运行的全库规则基线和独立评测器，**尚未接入 LLM/Agent 推理调用**。未来其他实验臂需要针对同一个被冻结的数据集写出 predictions.jsonl，最好同时写出自身实际的 trace.jsonl。之后调用：

~~~bash
job-rag-task evaluate \
  --run runtime/experiments/rag-tech-fixture-01 \
  --dataset experiments/rag-tech-requirements/fixtures.json \
  --gold experiments/rag-tech-requirements/gold.jsonl \
  --predictions /path/to/agent-predictions.jsonl \
  --trace /path/to/agent-trace.jsonl \
  --output runtime/experiments/agent-evaluation-01
~~~

最小预测记录：每个源岗位必须有一条，包括未命中者，不能只给 Top-K。

~~~json
{
  "job_id": "fx01",
  "in_scope": true,
  "technologies": [
    {
      "technology": "python",
      "requirement_level": "required",
      "alternative": false,
      "quote": "必须掌握 Python。",
      "start": 0,
      "end": 0
    }
  ]
}
~~~

上面偏移量只是 schema 占位，真实预测必须从原始 description 计算，满足 description[start:end] 与 quote 完全一致；绝不能照抄 0。技术类别与现有 technical_vocabulary.py 一致；新增 Java 等类别时需要版本化映射。外部预测必须使用新的 --output 保存评分结果，避免覆盖基线；没有外部实验臂自己的 trace 时，无法证明具体错误发生在检索、证据获取还是语义判断，报告会标记 undetermined，而不是借用规则基线的 trace。

## 如何判断哪里出错？

| 环节 | 要检查的事实 |
| --- | --- |
| source | 原文是否有证据，数据快照哈希是否一致 |
| section | 证据是否被正确归入职责或任职要求 |
| selection | 是否完整筛选符合口径的岗位 |
| evidence | 技术名词、原始区间是否正确获取 |
| interpretation | 否定、必备、优先、任选是否独立判断正确 |
| aggregation | 去重后各技术岗位数是否与逐岗位记录一致 |
| answer | 最终报告是否和汇总记录一致 |

错误按**最早有真实轨迹证据支持的环节**归因。没有上游轨迹时显示 undetermined。

指标只能在明确标注范围内解释：
- 岗位范围 Precision / Recall：已标注岗位。
- 技术证据召回：完成技术逐项标注的岗位；缺少标签不等于负例。
- 条件准确率：找到相应技术证据后的条件判断。
- 技术岗位数绝对误差：完整技术标注子集上的对比，不等于全库准确率。
- relation_to_rag 目前一律不做语义核验，不算入准确率。

16 个合成案例刻意包含现有技术词表缺失的 Java、以及同一句不同技术条件的误判。出现这些已知失败是正确的诊断输出，而不是框架出错。

## 下一步

优先对真实 JD 建设 20～40 条人工核验的结构化标注，复核章节识别、技术词表盲点、条件混合、是否直接用于 RAG 等失败。再保持同一任务、同一数据、同一评分器，逐次增加 LLM 理解臂、结构化抽取臂，以及确有必要时的 chunk/retrieval/rerank 臂。局部 Recall@K 升高不能直接宣称统计任务变好。
