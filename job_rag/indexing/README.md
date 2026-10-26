# 索引任务与执行器

本目录单独负责索引任务，避免把“导入原始数据”和“调用模型构建索引”混为一谈。

| 文件 | 职责 |
|---|---|
| `tasks.py` | `enqueue()`：在调用方事务中登记或重新激活指定岗位版本与索引签名的任务，不提交独立事务、不调用模型 |
| `worker.py` | `run_index_tasks()`：执行待处理或失败任务，调用独立分块器和可选 Embedding，原子替换岗位索引 |
| `worker.py` | `reindex()`：按当前配置登记全部岗位任务，然后执行索引 |

过期岗位版本或配置签名的任务标为 `obsolete`；失败时记录错误类型，不保存供应商响应或凭据，可重试。渲染后的块和索引签名不变时可复用已有向量；旧正文块会被替换，原始 JD 和岗位历史不被覆盖。

`worker`、`reindex` 和默认不带 `--no-index` 的 `import` 命令都可能触发模型调用。没有配置 Embedding 时使用关键词索引；已配置远端模型时应先确认预算，不能把这些命令视为无费用检查。

```python
from job_rag.indexing.worker import run_index_tasks, reindex
```

索引执行统一使用上述入口；测试或集成若需替换模型调用，应对实际执行位置 `job_rag.indexing.worker.embed` 打补丁。
