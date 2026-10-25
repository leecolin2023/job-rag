# Embedding 召回与 Rerank 两阶段实验

详细方案见 [实验协议](../docs/embedding-experiments.md)，结构化分块与迁移见 [分块说明](../docs/structured-chunking.md)。

`benchmark.v1.json` 包含30条查询、15个主题组（每组2种问法），14条 dev、16条 test。正例均附可在原始 CSV 中校验的引用。

**这是一套种子标注，不是穷尽的相关岗位集合。** 在候选池复核前，输出只能称为 `seed_recall@K` 等诊断指标。不能把未标注岗位当成真实负例，不能据此声称正式准确率提升。

## 快速使用

```bash
pip install -e '.[test,experiments]'

# 不调用 API：冻结数据、分块、基准和实现哈希
job-rag-experiment prepare --output runtime/experiments/prepared-v1

# 在自己的终端输入新 API Key，输入不会显示或进入 shell 命令历史。
# 如果此前已经创建了空配置，增加 --set-key；不要把 key 当成命令参数。
python3 scripts/setup_bailian_env.py \
  --host https://你的业务空间.cn-beijing.maas.aliyuncs.com

# 小规模模型/网络/凭据检查，会产生实际 API 请求
job-rag-experiment --max-requests 2 probe --execute

# 第一轮：同一 Embedding、同一查询与硬条件，仅比较文档方案
job-rag-experiment recall --prepared runtime/experiments/prepared-v1 \
  --output runtime/experiments/recall-v1 --candidate-limit 50 --execute
job-rag-experiment report runtime/experiments/recall-v1

# 汇集多方案候选，人工标注 grade=0..3、正例证据，最后 reviewed=true
job-rag-experiment pool --recall-run runtime/experiments/recall-v1 \
  --depth 50 --output runtime/experiments/review-v1.json

# 复核后可重新评分，不重复调用 Embedding
job-rag-experiment rescore --recall-run runtime/experiments/recall-v1 \
  --judgments runtime/experiments/review-v1.json --output runtime/experiments/recall-reviewed-v1

# 用 dev 选择召回 arm。下面 D 只是命令示例，不表示它已经胜出。
job-rag-experiment rerank --recall-run runtime/experiments/recall-v1 \
  --arm D_section_typed_1100 --judgments runtime/experiments/review-v1.json \
  --output runtime/experiments/rerank-v1 --execute
job-rag-experiment report runtime/experiments/rerank-v1
```

如仅想调试第二轮管线，可显式使用 `--allow-provisional`，但结果仍是种子标注诊断，不可作为正式结论。

所有快照、向量、候选、审阅文件、报告和请求日志均放在 `runtime/`，不提交 Git。API 配置只读本机 `.env.experiments` 或环境变量，不修改在线数据库或 `.env.docker`。
