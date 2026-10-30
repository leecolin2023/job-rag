# 完整 JD 重排输入审计（2026-10-28）

本次只核查公开文档、统计冻结候选并运行本地测试，没有调用付费模型，没有重建召回索引，没有修改历史实验快照或在线服务。

## 供应商当前限制

核查来源：[百炼文本排序 HTTP API](https://help.aliyun.com/zh/model-studio/text-rerank-api)、[Qwen3.7 模型信息](https://help.aliyun.com/zh/model-studio/qwen3-7-text-rerank)。

`qwen3.7-text-rerank` API 模型表列出：最多 500 份文档；单条输入 30,000 Token；请求输入建议不超过 120,000 Token。请求输入计算为 `query_tokens × document_count + sum(document_tokens)`，不是 JSON 请求字节数。模型信息页列出上下文 32,768；这里采用 API 表中更保守的文档限制。API 的 query 参数说明另写最大 4,000 Token，与模型概览的单条说明存在口径差异，代码采用更严格的 query 限制。按文档，单条超限返回 HTTP 400，不自动截断。

代码还将自定义 instruction 按每个 query/document 对重复计入预算，并为各文本保留 64 个估算单位。该保留量是软件策略，不是供应商公布的模板 Token 数。120,000 是 Qwen3.7 的供应商建议值，代码将其作为本地准入门槛。

未找到或验证本环境中与托管 Qwen3.7 对应的 tokenizer，因此不声称取得了实际 Token 数，也没有用旧版 Qwen tokenizer 代替。供应商返回的 usage 才能提供实际已处理用量。

## 已冻结候选的完整请求大小

来源：`runtime/experiments/recall-20261025-v1` 与其哈希绑定的 `prepared-20261025-v5`。共 30 个查询、6 个召回方案，即 180 组候选；每组候选 3–50 份。分别构造默认和招聘指令两种模型请求，共 360 个待发送请求变体。

下表为默认指令请求的 HTTP JSON UTF-8 大小（紧凑编码，包含字段和转义）。不是 Token 数，也不是已发送的网络流量。

| 召回方案 | 最小字节 | 中位字节 | 最大字节 | 默认保守预检通过 / 30 |
|---|---:|---:|---:|---:|
| A legacy | 6,518 | 130,131 | 166,957 | 8 |
| B compact | 6,518 | 127,291.5 | 171,430 | 8 |
| C section | 6,518 | 136,086 | 159,287 | 8 |
| D typed | 6,518 | 132,317 | 157,734 | 8 |
| E small | 6,518 | 135,447 | 159,654 | 7 |
| BM25 reference | 6,518 | 135,506 | 163,540 | 7 |

所有候选里最长的完整岗位表示为 14,054 字节。招聘指令版本各方案均为 7/30 通过保守预检。未通过主要是整批保守估算过大，**不能据此判断真实 Token 输入超限**。完整的 30 查询重排运行目前会在任何付费请求前停止，直到使用合适的 tokenizer 完成预算核实，或准备新的较小候选实验；不静默缩减已有候选。

## 实现变化与复现

- 同一份完整标题和 JD 原文用于所有重排对照；不重排章节、不截断正文。返回记录仍保留 `truncated=false`。
- 新增 `audit-rerank-inputs`，无需密钥、模型客户端或网络。结果含文档数、各类 UTF-8 字节大小、估算方法、限制和预检问题；不导出岗位全文。
- 默认计数方法为每段 UTF-8 字节数加 64；此方法是保守代理，不能与供应商 Token 数等同。加载本地 tokenizer 时记录其 SHA256，依然标记未由供应商验证。
- 整次实验和客户端发送前均检查输入。超限或无法由当前估算准入时明确失败，不自动截断、不拆批比较相对分数、不自动删除候选。
- 审计和新重排可以读取历史实现产生的冻结召回结果，仍校验全部源文件、准备 manifest 和候选结果哈希；新的审计和重排记录当前实现哈希。继续生成召回时仍要求准备阶段实现一致。

```bash
job-rag-experiment audit-rerank-inputs \
  --recall-run runtime/experiments/recall-20261025-v1

# 仅在确认 tokenizer 适用于托管模型后使用：
job-rag-experiment audit-rerank-inputs \
  --recall-run runtime/experiments/recall-20261025-v1 \
  --tokenizer-path /path/to/tokenizer.json
```

付费运行使用环境变量 `BAILIAN_RERANK_TOKENIZER_PATH` 指定同一文件。实际请求仍需显式 `--execute`，并需要完整候选审阅标签；本次没有执行这一步。

本机详细审计：`runtime/analysis/rerank-input-audit-20261028/requests.json` 和 `summary.json`，均位于 Git 忽略的运行目录。历史报告不覆盖，新旧文本表示的效果必须重新评测。
