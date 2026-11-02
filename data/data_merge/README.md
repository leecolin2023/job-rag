# 岗位采集合并：data_merge

此目录负责 **采集 CSV → 合并主表**，不承担爬虫、Embedding、数据库导入或检索。

- `../collections/YYYY-MM-DD/*.csv`：按采集日期存放的快照，只存 CSV，合并后不删除。
- `../jobs.csv`：唯一的岗位汇总表（12 个基础采集字段 + `analysis` 等人工附加列、UTF-8 BOM、`job_id` 唯一）。
- `merge_jobs.py`：按 ID 去重、更新及补充关键词的可重复执行脚本。
- `test_merge_jobs.py`：去重、字段保护和 CSV 转义测试。


## 岗位标识字段的定义

这几个字段不是四套不同的职位编号，而是**同一岗位在采集、汇总和数据库入库阶段的不同标识形式**。

| 字段 | 所在位置 | 定义和用途 | 生成或映射规则 |
|---|---|---|---|
| `职位ID` | `collections/YYYY-MM-DD/*.csv` | 采集平台上的职位标识；当前快照均来自 BOSS 直聘 | 由外部采集流程提供，通常对应职位详情 URL 中 `/job_detail/` 后、`.html` 前的部分；合并脚本不自行生成 |
| `job_id` | `data/jobs.csv`，以及数据库 `jobs.job_id` | 标准化后的**来源平台职位 ID**，用来识别同一来源上的重复采集记录 | `data_merge` 直接将 `职位ID` 映射为 `job_id`，不另外计算 UUID、哈希或自增值 |
| `source` | 导入参数及数据库 `jobs.source` | 职位来源平台，例如 `boss`；区分不同平台上可能相同的职位 ID | `job-rag import` 的 `--source` 参数，当前默认值为 `boss`；**不是** CSV 的搜索关键词 `keywords` |
| `key` | 数据库 `jobs.key`（主键） | 数据库中跨来源区分岗位记录的组合标识 | `key = f"{source}:{job_id}"`，例如 `boss:851936eee117332f0nx_2tu5FlZZ` |

例如，BOSS 直聘岗位详情地址：

```text
https://www.zhipin.com/job_detail/851936eee117332f0nx_2tu5FlZZ.html
```

对应的标识转换：

```text
采集 CSV：职位ID = 851936eee117332f0nx_2tu5FlZZ
             ↓ 直接映射，不重新生成 ID
汇总 CSV：job_id = 851936eee117332f0nx_2tu5FlZZ
             ↓ 导入时指定 source=boss
数据库： source = boss
        job_id = 851936eee117332f0nx_2tu5FlZZ
        key    = boss:851936eee117332f0nx_2tu5FlZZ
```

**当前去重的实际边界：**

- `data_merge/merge_jobs.py` 仅根据 `job_id` 字符串完全相等判断是否同一岗位；跨关键词、跨日期搜到相同 ID 会更新同一条记录，搜索关键词只作为来源线索合并。
- 相同公司、名称或 JD 但 **ID 不同** 的职位，仍视为两条记录。岗位关闭后重新发布并产生新 ID，也不会自动识别为同一招聘需求。
- `data/jobs.csv` **没有独立的 `source` 列**，目前合并流程以全部数据来自 BOSS 为前提。因此不同招聘平台出现相同 `job_id` 时，CSV 合并可能误合并；虽然数据库的 `source:job_id` 可以区分它们，但并不能自动修复主表阶段的碰撞。引入其他招聘平台前，应同步升级主表字段及合并键为 `(source, job_id)`。
- 当前合并器检查 ID 不能为空、单份快照内不能重复，但**尚未校验 `职位ID` 是否与岗位 URL 中的 ID 一致**。这属于未来应补充的采集数据质量校验，而非已实现功能。

## 使用

在仓库根目录：

```bash
python data/data_merge/merge_jobs.py --date 2026-10-31 --dry-run
python data/data_merge/merge_jobs.py --date 2026-10-31
python -m unittest discover -s data/data_merge -p 'test_merge_jobs.py'
```

也支持 `--input` 指定多个 CSV，`--master` 指定主表，`--output` 写到另一个文件。合并前可运行 `python scripts/report_dataset.py` 获取主表实时统计。自动合并工作流会处理最新日期目录的快照；处理历史日期请手动执行。

## 合并规则

1. 以 `职位ID` 对应 `job_id` 去重；保留历史岗位，单次采集未命中不能判定下线。
2. 只用采集时间不早于主表的记录更新有效字段；空值、“4”、“页面未显示”等占位符不覆盖旧数据。
3. 新采集只有城市时保留既有区/商圈信息；匿名“某公司”不覆盖已知公司名称。
4. `keywords` 追加去重，表示搜索关键词来源，不等价于正文真实技术要求。
5. 新岗位 `status=招聘中` 是台账标记，不代表实时验证；已有岗位的人工状态（含 `下线`）不会被自动覆盖。2026-10-31 起不再凭两批关键词检索的差集判断岗位下线。
6. 保留 JD 原文，CSV 安全转义，使用临时文件原子替换。合并不等于已同步数据库或已重建索引。
7. 写出时以 12 个基础字段开头，并原样保留主表已有的 `analysis` 和将来增加的其他人工字段；新岗位在未分析时这些列为空。合并器不读取或计算这些字段，不能让爬虫覆盖人工结论。

## 合并记录

- [2026-10-31 AI应用开发批次](merge_report_2026-10-31.md)：合并前 1,324，新增 472，合并后 1,796。
- [2026-11-01 大模型应用开发批次](merge_report_2026-11-01.md)：合并前 1,796，新增 315，合并后 2,111。
