# JD 结构化分块

本目录只负责从原始岗位记录生成与原文对齐的文档块，不读取 CSV、不操作数据库、不调用 Embedding，也不覆盖 `description`。

```text
chunking/
├── core.py        # 章节识别、条目边界、条件标签、预算与切块
├── legacy.py      # 保留原始固定分块方案，供历史对照
└── __init__.py    # build_documents() 等公共入口
```

原 `job_rag/chunking.py` 已改为同名包，`from job_rag.chunking import build_documents` 等公共导入保持不变。

## 输入与输出

- 输入：含 `description` 等字段的原始岗位字典，以及策略、长度和预算配置。
- 输出：`Document(text, details)` 列表。`text` 为带上下文头部的索引文本，`details` 保存原文字段片段、偏移、章节、条目、规则标签与版本信息。
- 空正文返回空列表，不生成虚构文字。
- 偏移按 Unicode 码点计，使用 `description[source_start:source_end]` 回取原文，不是 UTF-8 字节偏移。

## 主要步骤

1. `parse_sections()` 保守识别职责、任职要求、加分项、福利、公司介绍等章节；不能判断时保留 `unknown`。
2. `item_spans()` 尽量保留编号条目及续行上下文。
3. `condition_level()` 生成 `required`、`preferred`、`not_required`、`mixed`、`unspecified` 等规则提示；标签不是语义核验事实。
4. `build_documents()` 按预算合并或切分，记录原文范围和强制切分标记，便于回查否定、或关系及例外。

支持 `legacy`、`fixed_compact`、`section_compact`、`section_typed`。预算单位为字符、UTF-8 字节或显式提供本地 tokenizer 后的 token；不能把字符数当作模型计费 Token。固定对照策略只支持字符预算。

原固定分块算法统一通过 `chunking/legacy.py` 的 `legacy_documents()` 提供，仅用于历史方案对照，不再从标准化模块导出。需要文本列表时可从 `build_documents()` 的结果读取各块的 `text`。目录移动不改变切块算法、版本常量或索引签名配置。

## 与其他目录的关系

[预处理](../preprocessing/README.md)保存岗位并登记任务；[索引执行器](../indexing/README.md)调用这里的分块函数，按配置调用 Embedding，再将块与可选向量写入[存储层](../storage/README.md)。

详细设计见[结构化分块说明](../../docs/structured-chunking.md)。实验实现指纹改为覆盖新的源文件路径；旧冻结实验不改写，也不应为了兼容新目录而绕过实现指纹校验。历史实验应使用对应版本代码复核。
