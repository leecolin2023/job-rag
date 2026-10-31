# 岗位采集合并：data_merge

此目录负责 **采集 CSV → 合并主表**，不承担爬虫、Embedding、数据库导入或检索。

- `../collections/YYYY-MM-DD/*.csv`：按采集日期存放的快照，只存 CSV，合并后不删除。
- `../jobs.csv`：唯一的岗位汇总表（12 列、UTF-8 BOM、`job_id` 唯一）。
- `merge_jobs.py`：按 ID 去重、更新及补充关键词的可重复执行脚本。
- `test_merge_jobs.py`：去重、字段保护和 CSV 转义测试。

## 使用

在仓库根目录：

```bash
python data/data_merge/merge_jobs.py --date 2026-10-31 --dry-run
python data/data_merge/merge_jobs.py --date 2026-10-31
python -m unittest discover -s data/data_merge -p 'test_merge_jobs.py'
```

也支持 `--input` 指定多个 CSV，`--master` 指定主表，`--output` 写到另一个文件。自动合并工作流会处理最新日期目录的快照；处理历史日期请手动执行。

## 合并规则

1. 以 `职位ID` 对应 `job_id` 去重；保留历史岗位，单次采集未命中不能判定下线。
2. 只用采集时间不早于主表的记录更新有效字段；空值、“4”、“页面未显示”等占位符不覆盖旧数据。
3. 新采集只有城市时保留既有区/商圈信息；匿名“某公司”不覆盖已知公司名称。
4. `keywords` 追加去重，表示搜索关键词来源，不等价于正文真实技术要求。
5. 新岗位 `status=招聘中` 是台账标记，不代表实时验证；已有岗位的状态不会被自动覆盖。
6. 保留 JD 原文，CSV 安全转义，使用临时文件原子替换。合并不等于已同步数据库或已重建索引。

## 合并记录

- [2026-10-31 AI应用开发批次](merge_report_2026-10-31.md)：合并前 1,324，新增 472，合并后 1,796。
