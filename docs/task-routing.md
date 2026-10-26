# 按任务选择工具：第一批实现

本批不更换模型、不切换索引、不部署线上服务，也不运行付费评测。

代码目录已按职责整理：[服务接口](../job_rag/interfaces/README.md)、[候选检索](../job_rag/retrieval/README.md)、[精确查询](../job_rag/querying/README.md)。当前 `Catalog` 实现为 `job_rag/querying/catalog.py`，共享筛选规则位于同目录 `filters.py`，不依赖候选检索模块。

## 已实现与边界

- Agent和MCP说明按字面查找、语义查找、指定JD比较、统计、个人匹配、综合分析选择工具；不再强制查询改写或固定推荐数量。
- `POST /api/catalog` / MCP `query_job_catalog`：对全部原始岗位执行字面匹配与结构过滤，不经过索引、BM25、向量或Top-K，返回精确字面计数与分页列表。
- `POST /api/jobs/batch` / MCP `get_jobs_batch`：一次读取1—20份完整JD，逐项报告岗位不存在、版本变化；可绑定枚举时的corpus_id。
- 检索接口保留旧字段兼容调用者，但新增count_kind、count_complete，明确原total_candidates/total_matched不是总体数。
- 暂未实现自动全量语义判定任务、持久化判定结果、程序语义汇总器、跨调用费用/Token硬预算或独立路由模型。任务选择与普通查找3轮上限目前是Agent提示策略，不是后端强制执行的状态机。

## 字面查询契约

示例：广州原始JD中提到vLLM的岗位数量。

```json
{
  "terms": ["vLLM"],
  "fields": ["title", "description"],
  "operator": "and",
  "case_sensitive": false,
  "match_mode": "token",
  "filters": {"city": "广州"},
  "count_only": true
}
```

词法规则：

- fields仅支持title、description，不跨字段拼接匹配；每个词可出现在任一所选字段。
- operator为and或or，表示词之间的关系；terms=[]表示枚举全部结构条件内的岗位。
- substring为原样子串；token为前后均非Unicode字母、数字或下划线的边界。不是中文分词，也没有别名扩展或Unicode兼容归一化。
- case_sensitive=false使用Python casefold；词的空白不自动修剪，空白词和超过200字符的词拒绝。
- 结构条件不从自然语言自动推断。城市、区、学历按规范化值相等；experience_years是求职者经验能否满足岗位最低年限，不是岗位年限精确相等。
- 薪资单位为元，周期month/day/hour；lower_bound判断岗位下限是否达标，overlap按区间交叠。缺失数值不能判定为符合。
- skills保留既有字面AND含义，不表示任职必备条件。未知筛选字段拒绝，避免拼写错误悄悄放宽范围。
- 默认包括active与unknown，排除closed/suspected_expired；active_only只保留active，include_closed包含全部状态，二者不能同时启用。
- 以source+job_id计数；不会把近重复岗位自动合并。

`matched_jobs`为所选文本与结构规则下的完整岗位数，**不代表具备某能力，更不表示该能力是必备条件**。
`eligible_jobs`是字面匹配前通过结构与状态过滤的范围，missing_description_jobs及eligible_statuses描述此范围。
空正文岗位不会凭空排除：例如其标题仍可能命中。因此完整字面计数不意味着正文或知识库覆盖完整。

## 分页与一致性

1. 首次传terms、filters等条件，返回snapshot_id、corpus_id和next_offset。
2. 后续传相同条件、snapshot_id、offset=next_offset；page_size可调整。
3. 任何岗位内容、版本、状态或序列化元信息改变，或匹配条件改变，返回HTTP 409；MCP提示从头重来。不得将旧页与新页合并统计。
4. snapshot_id绑定数据与查询条件，corpus_id仅绑定数据。批量读取传corpus_id，可防止枚举与全文判断混用不同数据版本。

这是**乐观一致性校验**，不保存历史快照，不保证在频繁写入时仍能完成全量扫描。每次读取一个有序SQL结果，在Python遍历约600条原始数据；不是数据库级全文索引优化。将来数据规模或更新频率增长后再评估持久快照与数据库执行计划。

批量读取不会隐藏关闭岗位，便于比较历史JD；推荐前仍须核对状态。版本不匹配返回errors，不悄悄替换为最新全文；结果保留来源、URL、采集时间、状态、版本与完整raw。

## 路由验收场景

| 问题 | 期望行为 | 禁止行为 |
|---|---|---|
| 哪些岗位提到vLLM？ | 字面查询；按需分页 | 自动改写成SGLang后称原词命中 |
| 比较指定两个岗位 | 直接批量读取全文 | 先执行多查询召回 |
| 广州提到vLLM的岗位有多少？ | 全库字面计数，说明状态与匹配规则 | 计数Top-20 |
| 广州要求部署能力的岗位有多少？ | 定义口径、完整枚举与全文判断；无法完成则说明 | 把字面命中当能力满足，或代表性样本当总体 |
| 找三个适合我经验的RAG岗位 | 语义召回、按需补检索、全文核验 | 扩展查询时放宽薪资/经验条件 |
| 部署岗位有哪些能力组合？ | 分方向证据分析，说明样本范围 | 把样本频次称为全库比例 |

接口测试涵盖无索引75条结果的全量计数与分页、词法规则、硬过滤与状态、空正文、内容/状态/新增记录变化、条件绑定、批量错误与MCP工具契约。
上述路由表是后续真实Agent评测用例，**尚未调用付费模型验证执行成功率**；静态提示更新不能冒充行为评测。

## 下一批

语义条件判定协议（证据、条件性质、满足情况、版本）及可恢复全量任务；程序汇总符合/不符合/无法判断/未处理；检索循环硬预算与调用追踪；补齐多正例、近重复标注并发布经过审查的实际候选明细。现有历史实验和未提交的导出脚本保持不变。
