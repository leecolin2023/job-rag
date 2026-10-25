# Qwen3.7 Embedding / Rerank 实验协议

## 目标与边界

将两个问题分开：第一轮测文档方案对**召回覆盖**的影响，第二轮在同一候选集合上测**前排排序质量**。不在第二轮重新改写查询、增加召回源或偷偷放宽硬条件。

离线实验不连接在线岗位库，不更换线上容器，不自动提交/推送代码，也不自动将某个方案升为线上赢家。

## 百炼接入

已核实的官方文档（2026-10-25）：

- [通用文本向量同步接口](https://help.aliyun.com/zh/model-studio/text-embedding-synchronous-api)
- [文本排序接口](https://help.aliyun.com/zh/model-studio/text-rerank-api)

采用业务空间 API Host，不根据 API Key 猜测 Host。项目本机 `.env.experiments` 已配置用户提供的北京 Host；凭据由用户在自己的终端输入新值。

| 功能 | 模型 / 原生 HTTP 路径 |
|---|---|
| Embedding | `qwen3.7-text-embedding-flash`；`/api/v1/services/embeddings/text-embedding/text-embedding` |
| Rerank | `qwen3.7-text-rerank`；`/api/v1/services/rerank/text-rerank/text-rerank` |

Embedding 固定1024维、每批最多20条；查询使用 `parameters.text_type=query`，文档使用 `document`，均不额外添加 query instruct。文档所列 Flash 单条上限为128,000 Tokens；本实验短分块远小于该上限。Rerank 单次提交整个候选集合，避免把不同请求的相对分数直接拼起来比较。

新凭据不要贴到聊天中，也不要作为 CLI 参数传入。已经存在空配置时，在自己的终端执行：

```bash
python3 scripts/setup_bailian_env.py \
  --host https://llm-q9ba44cu7o2ffpnb.cn-beijing.maas.aliyuncs.com --set-key
```

输入隐藏，配置权限为0600；脚本仅替换本地 API Key。随后先执行 `job-rag-experiment --max-requests 2 probe --execute`。这一步才验证当前账户实际访问权限；官方文档支持模型不等于当前业务空间已经授权。

## 实验一：分块与召回

### 对照组

| Arm | 处理 | 主要比较因素 |
|---|---|---|
| A_legacy_1100 | 原始1100字符正文切分，完整重复头部 | 基线 |
| B_fixed_compact_1100 | 完全相同原文边界，只保留紧凑岗位头部 | A→B：去除重复结构化元数据 |
| C_section_compact_1100 | 章节/条目/条件边界，岗位与章节上下文 | B→C：结构化组织整体效果，非纯单因素标题消融 |
| D_section_typed_1100 | C的相同边界，额外添加条件性质提示 | C→D：条件标签文本提示 |
| E_section_typed_600 | D的小预算版本 | D→E：块大小与上下文覆盖权衡 |
| BM25_reference | 全岗位标题+描述的词法检索 | 无付费向量的参考组，不混入 dense arm |

所有 dense arm 固定同一模型、维度、查询和硬筛选；不使用Rerank、查询改写或Hybrid融合。结构化 C/D 预留相同头部预算，确保二者原文边界一致；原版 A 按历史规则只限制正文，渲染后总长度可能超过1100，因此不能将它误称为严格等 Token 对照。

固定快照包含592条可检索岗位。当前准备快照（`runtime/experiments/prepared-20261025-v5`）的块数依次为790、790、2443、2443、2657；这些是准备阶段统计，不是效果结果，后续解析规则变化后应以新快照为准。

### 召回与聚合

对全部满足条件的分块执行归一化向量精确余弦计算；先按岗位取最高块分数，再取Top-M（默认50）。不先取少量chunk再聚合，避免一个岗位的多个块挤掉其他岗位。

主指标为岗位级 Recall@5/10/20；同时看HitRate、每查询明细、块数和实际usage。记录Top-50以供第二轮冻结。chunk数量增加本身可能影响max聚合，因此要结合大小消融与人工错误分析，不将块多等同于理解好。

### 标注与分组

- 30条查询、15个主题组，涉及RAG、知识图谱、Harness、Web3、营销Agent、多模态、推理、运维、实习和产品。
- 每组两种表述，组内不跨dev/test；当前为14条dev、16条test。
- 每条有可验证原文的已知正例。它们是**种子正例**，不是全部相关岗位，准备阶段会拒绝不存在的引用或违反硬条件的正例。
- 初始指标命名为 `seed_recall@K` / `seed_ndcg@K`，不声称全量真实Recall。未标注样本不是负例；输出 `precision_lower_bound@K` 和 `judged_fraction@K` 供诊断，不用它们宣传正式准确率。
- 多系统候选池复核后使用 `pooled_*` 指标；只有覆盖所有满足硬条件的岗位、包含负例的穷尽标注，才允许无前缀 `recall@K` / `precision@K`。

使用dev选择方案，test只用于最终报告，不根据test结果反复调预算或规则。区间估计按主题组做配对cluster bootstrap（2000次，固定种子），不是把30条近似问法当作30个独立样本。当前组数较少，属于pilot实验，不能替代更大人工评测集。

## 候选池复核

`pool --depth 50` 合并所有系统Top-50及种子正例，按job_id排列，不展示来源系统和排名；seed_grade是参考信息，不自动成为最终评分。

人工逐条填写：

- `grade`: 0不相关、1部分相关、2相关、3直接匹配。
- `evidence`: 正例必须引用原文；执行时检查引用存在且满足硬条件。
- `reason`: 判断原因，特别是“优先不是必备”、否定、或关系和非AI Agent。
- 每条query的 `reviewed=true`：代表已审完其候选池，不是整个语料已经穷尽。
- `judgment_scope=pooled`：默认；不能为了获得无前缀指标直接改成exhaustive，程序会校验覆盖所有eligible岗位。

可用 `rescore` 重新给第一轮已保存的排名评分，不重复付费生成向量。人工修订与重评分作为新目录保存，不覆盖原实验。第二轮默认要求审阅标签；`--allow-provisional` 仅用于管线调试，结果必须标为临时诊断。

## 实验二：固定候选的重排

从第一轮**同一个 arm**保存的候选开始（只能根据dev选择，不预设 D 已胜出）。比较：

1. `none`：保留原始向量排名。
2. `bm25`：候选内词法重排。
3. `section_rule`：透明的章节/条目词法权重，并对明确必备意图下的优先/混合/不要求条目降权；不是逻辑证明器。
4. `qwen_default`：专用模型默认排序任务。
5. `qwen_recruitment_instruction`：同一个模型，增加招聘匹配、否定和优先条件说明，作为指令消融。

各方式使用相同岗位集合及同一份父文档表示，模型每次必须返回完整索引排列；缺少结果、重复索引或接口失败时中止，不偷偷回退并继续计算“模型效果”。

父文档表示优先保留任职要求、职责和加分章节，通常每岗最多1800 UTF-8字节；候选很多时缩减统一预算，以保守控制请求大小。截断显式记录，预算不是实际Token；所有重排方案使用同一截断版本。需结合 `representations` 抽查截断是否损伤关键信息，表示优化应作为后续单独实验，不能混入模型重排消融。

主指标为 nDCG@5、Precision@5、MRR；同时记录原候选的Recall上限。Rerank只能改变已有候选的顺序，不能找回没有召回的岗位，因此不把Top-M覆盖率不变当成失败。专用模型分数是单请求相对分数，不视作跨请求概率或统一阈值。

## 可复现与费用保护

- `prepare` 无API请求：冻结CSV哈希、查询、正例、分块、原文偏移、策略、预算及实现哈希；源代码/快照变化需要新prepare。
- 向量缓存键包含Host、模型、维度、query/document类型及精确文本；不同方案相同文本复用，避免重复收费。
- 候选与排名保存并校验哈希；不能修改第二轮候选后继续使用旧manifest。
- `--execute` 明确确认调用；`--max-requests` 限制实际HTTP次数，重试计入上限。
- `--max-cost-cny` 增加软件费用保护：以核实过的北京公开价格及usage累计，发送前使用UTF-8代理量和前缀余量估算下一请求。未知计费的失败请求保守预留，缓存命中不计新调用。该估算**不是平台账单硬限额**，免费额度、折扣及供应商Token规则仍以平台为准。当前Embedding首轮使用0.50元保护及500请求上限。
- 401/403/404等配置/授权错误不反复重试；429/部分5xx有限重试。传输失败可能已计费，日志标记不确定，不能保证exactly-once账单。
- 请求日志只存模型、内容哈希、request_id、状态、时延及usage计数，不写凭据/请求正文。按usage统计真实Token，不拿字符数估算为实际账单。
- 缓存命中的耗时不是模型网络时延；Rerank结果记录cache_hit，真实请求时延见请求日志。
- 模型别名可能由供应商滚动更新；保留运行时间、request_id及实际向量缓存。不同日期的无缓存重跑不保证后端权重完全一致，不将“模型名相同”视为严格的供应商版本固定。

输出在 `runtime/experiments/`：准备快照、SQLite向量缓存、请求JSONL、每查询排名、summary.json、report.md与metrics.csv。该目录和实值环境配置被Git忽略，发布结论前仍须人工核对脱敏与标注范围。

## 当前状态

已完成结构处理、快照准备、API适配及实验基准设计；76项测试通过，并在独立PostgreSQL数据库中验证了显式迁移与真实pgvector操作（测试向量，不是Qwen输出）。正文覆盖审计未发现非空白内容丢失；95条岗位仍无法可靠归入明确章节，保守保留unknown，需人工抽查。

用户已明确授权使用其提供的凭据，实值仅保存在本机受限配置。真实Embedding已返回1024维向量；真实Rerank小探针也通过。该业务空间的Embedding返回`index`（不同于部分文档示例的`text_index`），适配器已兼容并严格校验两种格式。首轮真实召回实验已完成，详见[结果与限制](recall-pilot-2026-10-25.md)；348次成功响应报告1,531,082输入Token，usage对应公开价格估算约0.1914元。第二轮全量重排尚未执行，不能宣称准确率已提升。当前在线服务未迁移/切换。

可使用 `python scripts/summarize_experiment_usage.py --journal <manifest中的request_journal>` 分析HTTP次数、usage和公开价格估算费用；不指定journal时汇总所有真实实验请求（包括已被平台接受但客户端解析失败的探针）。该输出不等于账户实际账单。
