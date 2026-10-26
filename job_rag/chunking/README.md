# JD 分块：怎样让检索命中具体招聘要求，又能回到原文？

岗位详情并非一段均匀文本。公司介绍里出现 “vLLM”，和“任职要求：熟练部署 vLLM”表达的是两件事。如果把长 JD 任意截成固定长度，可能刚好把标题、否定词和“优先”条件切掉；检索能命中一个技术词，却无法解释招聘方到底要求什么。因此 `chunking/` 同时处理**语义组织的基本结构**和**原文可追溯的位置**。

## 一、输入和输出是什么？

输入是一条带 `description` 的原始岗位字典，输出是若干 `Document(text, details)`。`text` 是真正参与 BM25/Embedding 的检索表示，通常包含“岗位标题、章节标题、条件性质提示、原文片段”；`details` 保存章节类型、原文片段、起止偏移、分块策略与版本等元数据。它不读取 CSV、不操作数据库，也不调用模型。

例如，一条“任职要求”下的 `vLLM` 描述，会以对应章节头部加原句组成检索块；`details.section_type` 记录 `requirements`。源位置按 Unicode 码点计算，可以用 `description[source_start:source_end]` 取回原句，不能当 UTF-8 字节下标。

## 二、具体如何完成分块？

`core.py` 先用 `parse_sections()` 识别“岗位职责”“任职要求”“加分项”等标题。无法可靠识别的区域保留为 `unknown`，而不是把所有文字误判成任职要求。

随后 `item_spans()` 按编号、项目符号及续行拆出条目；`condition_level()` 根据明确的词法条件标注 `required`、`preferred`、`not_required`、`mixed` 或 `unspecified`。例如一句同时出现“必须”与“优先”、或存在“满足其一”等替代条件，会保守标记为混合或不确定，供后续阅读原文判断。

最后 `build_documents()` 在预算内合并相容条目；太长时优先沿完整句子切分，必须强制截断时记录 `hard_split` 和条目关联位置。没有正文就返回空列表。**这里的 required 等是规则提示，不是模型核验过的招聘事实。**

## 三、为什么不只有一种分块大小？

项目保留四种策略以便实际比较：

| 策略 | 文本组织方式 | 主要用途 |
|---|---|---|
| `legacy` | 旧版分段和较完整的重复岗位头部 | 与历史检索方案对照 |
| `fixed_compact` | 沿用旧边界，减少重复头部内容 | 区分头部噪声的影响 |
| `section_compact` | 尽量沿章节和条目边界组织 | 观察结构是否有帮助 |
| `section_typed` | 在结构化边界上增加条件提示 | 观察“必备/优先”提示的作用 |

默认配置使用 `section_typed`、预算 1100 **字符**。也支持 UTF-8 字节预算；只有显式提供本地 tokenizer 时才能按 Token 预算。字符、字节不是远端供应商的真实计费 Token，不能互相混用。

更小的块不一定更好：它让局部要求更突出，也可能把工作目标和约束分开。此前离线实验存在改善与退化同时出现的情况，因此不因“结构化更复杂”就认定召回必然提高。

## 四、与其他模块怎样协作？

`indexing/worker.py` 负责调用 `build_documents()`，再选择是否通过 `providers` 生成向量并把块写入 `storage.chunks`；`retrieval` 命中 Chunk 后返回文字与 `details`，必要时扩展到完整章节或 JD。原先的固定分块函数放在 `legacy.py` 供对照，公共入口仍可用 `from job_rag.chunking import build_documents`。

阅读[索引流程](../indexing/README.md)可以继续理解块如何变成可用索引；[分块实验说明](../../docs/structured-chunking.md)提供更完整的历史对照背景。