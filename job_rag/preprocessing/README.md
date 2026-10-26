# 原始数据预处理

本目录负责把[原始 CSV](../../data/README.md)变为可追溯的岗位记录：校验输入、派生标准字段、事务内增量导入。**不包含爬虫，不改写 JD，不调用大模型，也不执行分块或 Embedding。**

## 目录与处理顺序

```text
preprocessing/
├── validation.py    # parse_csv()：整份 CSV 校验
├── normalize.py     # normalize()：规则标准化；数据指纹
├── importer.py      # import_csv()：增量入库与版本留存
└── __init__.py      # 校验与标准化公共入口
```

```text
CSV 字节 → parse_csv() 整份校验 → 数据库事务
                                   ├── normalize() 派生标准字段
                                   ├── 保存原文与历史版本
                                   └── 登记索引任务（不在此执行）
```

CSV 校验、标准化与增量导入统一由本目录提供，不再保留根目录下的旧模块兼容入口。各函数的导入路径见下方示例。

## 1. CSV 校验：`validation.py::parse_csv()`

导入前先验证整份输入：

- 字节输入用 `utf-8-sig` 解码，兼容 BOM；同时支持已解码字符串。
- 必需列为 `job_id`、`title`、`company`、`location`、`salary`、`experience`、`education`、`url`、`description`、`status`、`collected_at`。
- 检查记录字段数量与表头是否一致，拒绝空 `job_id`、同一批 CSV 中重复的 `job_id` 和无记录文件。
- `description` 保留解析出的文字、首尾空白和换行；其他字段裁剪首尾空格。
- 使用标准 CSV 解析器处理引号和多行正文；这是现有业务校验，不是所有 CSV 语法问题的穷尽检测，也不核验网页是否真实或仍在招。

`import_csv()` 在全部记录校验成功后才开启数据库事务。末条记录出错不会留下前面已导入的部分岗位；事务中途发生异常也会整体回滚。

必需列不等于每个值必须非空：正文允许为空，并在下一步记录质量标记。CSV 行数不等于岗位数，因为正文可能跨行。

## 2. 字段标准化：`normalize.py::normalize()`

将人可读的招聘字段转为程序可比较的字段，完全使用字符串解析、正则和规则，不需要 LLM。

原始输入示例：

```text
location：广州·天河区
salary：20-35K·14薪
experience：3-5年
education：本科
```

派生结果（节选）：

```json
{
  "city": "广州",
  "district": "天河区",
  "salary_min": 20000,
  "salary_max": 35000,
  "salary_period": "month",
  "salary_months": 14,
  "experience_min": 3,
  "experience_max": 5,
  "education_level": "本科"
}
```

其他派生字段包括 `employment_type` 和 `quality_flags`。月薪转换为元，日薪、时薪分别记录周期，不直接混比；薪资解析先执行 NFKC 兼容字符归一化，但不覆盖原始薪资文字。

### 两个关键约束

1. **上下限分别保存。** “岗位薪资下限达到 20K”检查 `salary_min >= 20000`；“岗位区间覆盖 20K”使用另一筛选口径。例如 `10-25K` 不满足前者，却覆盖 20K。筛选在检索层执行，不在预处理中替用户选口径。
2. **无法解析不猜测。** “面议”保留 `salary_min = null`、`salary_max = null`、`salary_period = "unknown"`，并记录 `salary_not_comparable`。这保证规则可复现，但会漏掉规则尚未覆盖的有效表达，不能把解析失败当作岗位没有该条件。

质量标记包括：`missing_description`（正文缺失）、`source_fields_unknown`（出现“页面未显示”）、`mixed_experience_field`（经验栏混入学历文字）、`salary_not_comparable`（薪资暂不能数值比较）。这些是数据质量提示，不是岗位相关性或招聘状态判断。

## 3. 岗位增量导入：`importer.py::import_csv()`

唯一键为：

```python
key = f"{source}:{row['job_id']}"
```

默认来源为 `boss`；同一 ID 可在不同来源下分别保存。来源参数必须为 1—60 字符且不含冒号。

| 情况 | 处理方式 |
|---|---|
| 全新岗位 | 创建版本 1，保存原始字段、标准字段与历史版本，登记索引任务 |
| 导入字段变化 | 版本号加 1，保存新记录与历史版本，登记索引任务 |
| 完全相同 | 更新本系统最近观察时间；索引未就绪或签名变化时重新登记任务 |

`raw_hash` 对解析并处理后的全部导入字段计算指纹，所以仅采集时间变化也会产生新版本；`content_hash` 只覆盖指定内容字段。它们不是对原 CSV 文件字节的哈希，也不是近重复语义识别。

新岗位的招聘状态始终初始化为 `unknown`，不能由 CSV 的采集 `status` 推断为在招。重复导入也不会把已经关闭的岗位自动恢复为在招。

**新 CSV 缺少某个岗位，不会自动关闭或删除它。** 缺失可能来自排序变化、反爬或加载失败，不能作为职位关闭依据。最近观察时间也不是最近核验时间。

## 4. 如何使用与下一阶段

```python
from job_rag.preprocessing.validation import parse_csv
from job_rag.preprocessing.normalize import normalize
from job_rag.preprocessing.importer import import_csv
```

从项目根目录运行 `.venv/bin/job-rag import data/jobs.csv --no-index` 可仅导入并登记任务；不加 `--no-index` 时，CLI 还会调用独立索引执行器，不能把整个 CLI 命令误称为“纯预处理”。

- 数据写到哪里、有哪些表：[storage/README.md](../storage/README.md)。
- JD 如何分节和切块：[chunking/README.md](../chunking/README.md)。
- 谁调用 Embedding 并更新索引：[indexing/README.md](../indexing/README.md)。
