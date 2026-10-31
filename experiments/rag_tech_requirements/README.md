# RAG 岗位技术要求统计：如何设计一场可验证的实验？

## 文件结构与职责

本目录把**同一道业务统计题**的测试数据、标准答案、规则实现、评分逻辑和测试集中保存。按下面的顺序阅读，就能知道每个文件解决什么问题：

```text
experiments/rag_tech_requirements/
├── README.md                 # 实验问题、评测设计、运行方法（本文件）
├── fixtures.json             # 试卷：16 条专门设计的模拟岗位
├── gold.jsonl                # 参考答案：逐岗位的正确范围和技术标签
├── task_runner.py            # 答题：扫描 JD、提取技术、生成预测与统计
├── task_eval.py              # 阅卷：预测与 gold 对比，计算指标和错误归因
├── task_review.py            # 出真题：从真实 jobs.csv 抽样生成待人工复核的队列
├── test_task_experiments.py  # 自动化测试：检查运行、评分、证据与数据安全边界
└── __init__.py               # Python 包标记，让同目录代码可以相互导入
```

| 文件 | 为什么需要它？ | 什么时候看？ |
| --- | --- | --- |
| `README.md` | 解释我们统计什么、用什么口径、怎样判断系统是否答对 | 第一次理解或调整实验时 |
| `fixtures.json` | 提供能覆盖否定、加分、任选、章节等边界的**模拟 JD** | 设计新的失败案例时 |
| `gold.jsonl` | 给这些 JD 预先定义**标准答案**，不依赖程序自己的预测 | 检查标签或更新实验口径时 |
| `task_runner.py` | 实现当前**纯规则基线**，写出逐岗位预测、过程轨迹及统计结果 | 统计数字异常，或准备替换算法时 |
| `task_eval.py` | 拿预测和标准答案比较，评估筛选、技术提取、条件判断与计数错误 | 理解错误报告、改进评分时 |
| `task_review.py` | 从真实岗位中分层抽样，生成**尚未审核**的人工核验队列 | 准备建立真实岗位 gold 时 |
| `test_task_experiments.py` | 运行自动化回归测试，防止搬目录或改规则后破坏原功能 | 每次修改代码后 |
| `__init__.py` | 支持用 `experiments.rag_tech_requirements` 导入模块 | 通常不需要修改 |

最重要的文件关系：

```text
fixtures.json（模拟岗位） ──→ task_runner.py（答题） ──→ predictions.jsonl
                                       │                           │
gold.jsonl（标准答案） ─────────────────────────────→ task_eval.py（阅卷）
                                                                   │
                                                                   ▼
                                                           evaluation.md（成绩）

data/jobs.csv（真实岗位） ──→ task_review.py ──→ review_queue.jsonl（待人工核验）
```

**目录外仍有三个共享部分**：`experiments/cli.py` 是所有实验共用的命令入口；`job_rag/` 提供生产代码中的章节识别、技术词表和条件规则；`data/jobs.csv` 是所有实验都可以使用的岗位主表。它们不属于本题独有实现，因此不移动。运行生成的报告、预测与轨迹放在 `runtime/experiments/`，**不提交到 Git**。

> **业务问题**：统计岗位职责或者任职要求出现 RAG 的岗位中，相关的技术要求是什么？

这份实验不是先比较 Embedding、Rerank 或 Agent，而是先回答一个更基础的问题：**对于一批已知岗位，程序能否准确筛选目标岗位、提取技术要求，并生成可核对的统计结果？**

当前已有一套**不调用大模型的规则基线**，可以完整扫描岗位数据并生成统计报告；另有 16 条模拟岗位及其标准答案，用来检查规则在哪里出错。**真实岗位的语义准确率、LLM/Agent 对比实验尚未完成。**

阅读顺序：先理解第 1～4 节的实验原理；需要运行时直接看第 5 节；希望扩展到 Agent 时看第 6 节。

## 1. 任务口径

1. **筛选**：职责或任职要求出现独立 RAG 字面词，大小写不敏感；GraphRAG、RAGFlow 默认不自动算作独立 RAG。仅公司介绍或加分项提到 RAG，不纳入统计。
2. **否定**：「不要求 RAG」也属于字面出现，但绝不等于岗位要求该技能。统计范围与语义条件是两件事。
3. **技术**：逐项区分职责涉及、明确必备、优先、否定、任选、未明确；是否与 RAG 直接相关需单独审阅。
4. **计数**：同一岗位同一技术出现多次只计一个岗位。不同技术类别可以重叠，不允许相加作为总岗位数。
5. **未知章节**：单列待复核，不可默认为不符合。
6. **统计边界**：当前 CSV 是已采集的岗位集合，不是整个招聘市场，也不证明岗位正在招聘。

**当前实现边界**：技术提取只扫描职责和任职要求，独立「加分项」章节的技术暂未统计（例如 `fx01` 的 Milvus）。这是现行实现与标准答案的一部分；若要覆盖完整的优先技术要求，应同步调整任务口径、标准答案和程序，而不只是修改报告措辞。

## 2. 模拟岗位与标准答案

运行 `jobs.csv` 可以得到「某技术出现于 N 个岗位」的报告，但如果没有一份独立的正确答案，就无法知道 N 是否准确。

这和考试相似：必须有**试卷、参考答案和阅卷方法**，否则程序输出得再像样，也无法判断是否真的完成任务。

### 2.1 模拟案例及覆盖的失败类型

[fixtures.json](fixtures.json) 是 16 条人为构造的 JD；[gold.jsonl](gold.jsonl) 是针对这些 JD 预先写好的标准答案。它们专门覆盖不同的失败情况，而不是随机拼凑 16 个岗位：

| 案例 | JD 的关键表达 | 主要考点 |
| --- | --- | --- |
| fx02 | 公司介绍使用 RAG | 能否排除错误章节 |
| fx03 | 开发 GraphRAG | 能否识别独立单词边界 |
| fx04 | 不要求 RAG；无需 Python | 字面命中与否定判断能否分开 |
| fx05 | Python 优先；Java 必须 | 能否分别判断两个技术的条件 |
| fx06 | Python 或 Java 至少一种 | 能否保留任选关系 |
| fx07 | Milvus 出现两次 | 能否按岗位去重 |
| fx08 | 一份较长 JD，末尾要求 Docker | 长文本中的信息会不会遗漏 |
| fx09 | 无章节标题 | 会不会把未知强行归为不符合 |
| fx10 | 公司介绍提到 Docker | 会不会把其他章节的技术算入 |
| fx11 | 仅加分项出现 RAG | 会不会扩大岗位范围 |

另外几条用于覆盖部署、框架、向量检索以及同一句话中不同条件混杂的情况。

### 2.2 标准答案的标注要求

对于每份 JD，先标明**是否符合范围**；只有符合范围且完成技术核验的 JD，才逐项记录技术类别、原文片段和条件标签。用 `tech_review_complete: true` 表示「这份 JD 的技术标注已经完整」，不能把尚未标注的技术默认看成不存在。

当前 16 条是**合成规格答案（synthetic_spec）**，它们用来验证程序是否符合这套规则，**不是**真实招聘 JD 已经由人工确认的证据。

### 2.3 为什么保留已知失败案例

例如 `fx05` 的标准答案包含「Java—必备」，但当前 [技术词表](../../job_rag/querying/technical_vocabulary.py) 没有 Java 类别，因此规则程序会漏掉它。这个失败很有价值：它明确告诉我们**需要补技术识别能力**，而不是笼统地说整个 RAG 效果不好。

测试集不应为了让当前程序得高分而删掉难例。实验的目的就是**暴露可定位的缺陷**。

## 3. 规则基线的统计流程

[task_runner.py](task_runner.py) 使用**完整 JD 扫描**，不依赖向量索引，也不使用 Top-K 检索，流程如下：

```text
完整岗位数据
  ↓ 1. source：读取每个 JD，记录原文指纹
  ↓ 2. section：识别职责、任职要求、加分项等章节
  ↓ 3. selection：仅在规定章节寻找独立 RAG
  ↓ 4. evidence：查找已收录的技术词，保留原文位置
  ↓ 5. interpretation：用规则推断必备、优先、否定、任选
  ↓ 6. aggregation：按 job_id + 技术类别去重计数
  ↓ 7. answer：把聚合结果填入 Markdown 报告
```

注意三个实现上的取舍。

**为什么完整扫描，而不是 Top-K 检索？** 这是在一个已知且可遍历的 CSV 上做全量统计。如果只取相关度最高的 20 个岗位，其他符合条件的岗位可能直接漏掉。此任务的第一版应优先保证扫描覆盖，故 `chunking` 和 `retrieval` 标为 `not_applicable`，不是这两项能力已经通过评测。

**为什么先使用规则而不是 LLM？** 规则方法简单、便宜、可复现，适合作为基线；后续接入 LLM 才知道它真正解决了哪些问题。规则也有明显限制：技术词表可能漏词，复杂句子中的「优先/必须」可能互相污染，更无法凭技术词共现证明它与 RAG 的业务关联。

**为什么保留中间过程（trace）？** 只看最终数字，无法区分「岗位没筛进来」「技术没提出来」与「条件理解错了」。记录真实处理过程后，才有可能把错误定位到对应环节。

## 4. 评测指标与错误定位

[task_eval.py](task_eval.py) 将程序输出（`predictions`）与独立标准答案（`gold`）逐岗位比较。

### 4.1 岗位范围

- **Precision（精确率）**：程序纳入的已标注岗位中，有多少确实应该纳入？低了说明误筛多。
- **Recall（召回率）**：应纳入的已标注岗位中，程序找到了多少？低了说明漏筛多。

这两个指标只回答**筛选范围**是否正确，不代表技术提取得好。

### 4.2 技术证据

**技术证据召回率**衡量已完整标注的技术事实有多少被找到。发现 `Java` 被漏掉，通常先排查技术词表或证据提取，而不是去优化 Rerank。

匹配技术时还需要核对原文证据；仅仅在预测和标准答案中都有 `python`，不足以证明提取了正确的那处文字。

### 4.3 技术要求程度

**条件准确率**只在已经匹配到技术证据的事实中计算。它检验「Python 优先」是否被判断为优先、「无需 Python」是否被判断为否定，以及任选关系是否保留。不能把遗漏的技术拿来当条件判断正确。

### 4.4 技术岗位数

**技术岗位数绝对误差** = |程序统计的岗位数 − 标准答案中的岗位数|。

例如完整标注样本中，Python 的标准数量是 8，程序数出 10，误差就是 2。只有在**技术逐项标注完整的子集**上，才有资格做这个比较；不能把 40 条人工样本的误差冒充整个 `jobs.csv` 的准确率。

### 4.5 错误定位

| 最早出现问题的环节 | 典型现象 | 应该优先检查 |
| --- | --- | --- |
| section | 把公司介绍当任职要求 | 章节识别规则 |
| selection | 应纳入的 RAG 岗位被漏掉 | 筛选条件与词边界 |
| evidence | JD 有 Java，但没抽到 | 技术词表、原文定位 |
| interpretation | 「优先」误判为「必备」 | 条件作用范围与语义理解 |
| aggregation | 同一岗位重复计数 | 去重键与类别归并 |
| answer | 报告和汇总文件不一致 | 报告生成逻辑 |

错误按**最早有实际轨迹证据支持的阶段**归因。如果外部 Agent 没有提供自己的中间过程，就标记为 `undetermined`，不能拿规则程序的轨迹冒充 Agent 的轨迹。

## 5. 运行实验

所有命令从仓库根目录执行，统一使用 `job-rag-experiment`。当前任务基线不调用百炼、不产生付费模型请求、不更改生产索引。

### 5.1 第一步：用模拟 JD 给规则程序“考试”

```bash
pip install -e '.[test,experiments]'

job-rag-experiment run \
  --dataset experiments/rag_tech_requirements/fixtures.json \
  --gold experiments/rag_tech_requirements/gold.jsonl \
  --output runtime/experiments/rag-tech-fixture-01
```

这会同时生成规则预测和评测结果。建议先打开 `evaluation.md` 看成绩，再去 `evaluation.json` 找具体错误；如果需要追查是哪一步造成错误，再看 `trace.jsonl`。

只想更换评分逻辑、重新评测**同一批已经算出的预测**，不用重跑基线：

```bash
job-rag-experiment evaluate \
  --run runtime/experiments/rag-tech-fixture-01 \
  --dataset experiments/rag_tech_requirements/fixtures.json \
  --gold experiments/rag_tech_requirements/gold.jsonl
```

### 5.2 第二步：在真实岗位库中生成字面统计报告

```bash
job-rag-experiment run \
  --dataset data/jobs.csv \
  --output runtime/experiments/rag-tech-corpus-01
```

先看 `report.md`：它给出符合当前字面口径的岗位数及各技术的**词面共现数量**。这是一份可检查的基线统计，**不是已经通过语义核验的招聘技术要求结论**。

### 5.3 第三步：抽取真实岗位，建立人工标准答案

```bash
job-rag-experiment prepare-review \
  --dataset data/jobs.csv \
  --limit 40 \
  --output runtime/experiments/rag-tech-review-01
```

[task_review.py](task_review.py) 会按字面命中、未知章节、GraphRAG/RAGFlow 边界、非目标章节命中、普通负例进行分层抽样，输出 `review_queue.jsonl`。每条保留完整 JD 和规则建议，供人独立复核。

这里生成的是 **pending_review 待审队列，不是 gold**。审阅后应另建真实 JD 的 `gold.jsonl`，明确 `label_source: human_reviewed`、原文证据、技术标注是否完整，并保留 `description_sha256` 防止 JD 变动后仍沿用旧标签。建议先做 20～40 条覆盖典型失败的样本，再扩大规模。

每次 `--output` 都必须使用**尚不存在的新目录**，以免覆盖之前的实验。

### 5.4 输出文件说明

| 输出文件 | 什么时候看 |
| --- | --- |
| `report.md` | 想知道本次统计得到什么结果 |
| `evaluation.md` | 想快速知道模拟/已标注样本的评测成绩 |
| `predictions.jsonl` | 想检查某个岗位被怎样筛选、提取了什么技术 |
| `trace.jsonl` | 想定位处理过程中的具体失败环节 |
| `summary.json` | 需要程序读取各技术类别的计数 |
| `evaluation.json` | 需要逐条分析错误、指标明细 |
| `manifest.json` | 需要确认数据哈希、规则/词表版本是否一致 |

提供 gold 运行时才会产生 `evaluation.md` 和 `evaluation.json`。审阅队列另有 `review_queue.jsonl`、`review_manifest.json`。运行产物保存在被 Git 忽略的 `runtime/experiments/`。

## 6. LLM 与 Agent 对照实验

当前**尚未接入 LLM/Agent 推理调用**。扩展时要保持**同一个问题、同一份数据快照、同一套 gold、同一个评分器**，只替换完成任务的方法，例如：

| 实验方案 | 要比较的改进 |
| --- | --- |
| A：现有完整扫描 + 规则 | 零模型成本的基线 |
| B：完整扫描 + LLM 结构化抽取 | 能否补全技术词、改善复杂条件理解 |
| C：LLM/Agent + 工具与迭代检查 | 能否主动发现遗漏并验证最终计数 |
| D：Chunk/Retrieval/Rerank（确有需要时） | 数据过大无法全量输入时，是否仍能保证统计覆盖 |

不能因为 D 的局部 Recall@K 变高，就认为**全库统计**更准确。真正要比较的是岗位范围、技术证据、条件和最终计数是否整体变好。

外部方案须对**数据集每个 job_id**写出一条 `predictions.jsonl`，包括未命中岗位，不可只返回 Top-K。技术类别应遵循当前 [technical_vocabulary.py](../../job_rag/querying/technical_vocabulary.py) 的版本；原文引用必须有真实 `start/end` 位置，满足 `description[start:end] == quote`，不能填占位偏移量。最好同时输出**该方案自己的** `trace.jsonl`，否则只能评分结果，无法证明其内部错误发生在哪一步。

已有预测文件后，可用同一个评测器评分：

```bash
job-rag-experiment evaluate \
  --run runtime/experiments/rag-tech-fixture-01 \
  --dataset experiments/rag_tech_requirements/fixtures.json \
  --gold experiments/rag_tech_requirements/gold.jsonl \
  --predictions /path/to/agent-predictions.jsonl \
  --trace /path/to/agent-trace.jsonl \
  --output runtime/experiments/agent-evaluation-01
```

`--trace` 可省略，但不能据此声称已经定位 Agent 的内部错误；外部预测必须写入新的 `--output` 目录。正式比较真实 JD 时，应使用**与该真实数据快照匹配的 run 和人工 gold**，不能套用模拟岗位的路径。

## 7. 当前进展与下一步

**已经具备**：固定的字面任务口径、16 条模拟 JD、合成标准答案、全量规则基线、逐岗位结果与处理轨迹、独立评分器、真实岗位待审抽样工具。

**尚未证明**：真实岗位的语义准确率、技术是否直接服务于 RAG、加分技术的完整覆盖、LLM/Agent 相比规则的提升，以及整个招聘市场中的技术要求分布。`jobs.csv` 仅代表已采集记录，也不能仅凭数据存在就认定岗位仍在招聘。

下一步按影响真实业务结论的优先级推进：

1. **先审统计口径**：是否要纳入独立加分项的技术？是否把「字面出现 RAG」升级为「实质要求 RAG 能力」？这些改动应先修订题目与 gold，再改程序。
2. **建立真实 gold**：人工审阅 20～40 条有代表性的 JD，保留原文证据和未决状态，避免用规则预测充当标准答案。
3. **对照具体失败改进**：先查漏掉的技术（如 Java）、复杂条件的误判、章节识别，再尝试 LLM 结构化抽取。
4. **最后决定是否需要 Agent 和检索**：只有当真实任务出现单次抽取解决不了的跨岗位核对、数据过大或遗漏发现问题时，才引入更复杂的步骤。

相关实现：[task_runner.py](task_runner.py)（规则运行）｜[task_eval.py](task_eval.py)（评测）｜[task_review.py](task_review.py)（待审抽样）｜[统一实验入口](../README.md)（旧检索实验与 CLI）。
