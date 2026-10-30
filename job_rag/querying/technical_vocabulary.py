"""Versioned, inspectable categories for literal technical mentions."""

VOCABULARY_VERSION = "technical-mentions-v1"
TECHNOLOGIES = {
    "agent_workflow_tools": ("Agent/工作流/工具调用", r"agent|智能体|工作流|workflow|function\s*calling|tool\s*(?:use|calling)"),
    "python": ("Python", r"(?<![a-z])python(?![a-z])"),
    "prompt_context": ("Prompt/提示工程/上下文工程", r"prompt|提示词|提示工程|上下文(?:工程|管理|优化)"),
    "api_backend": ("API/后端服务集成", r"(?<![a-z])api(?![a-z])|fastapi|flask|django|spring\s*(?:boot|ai)|后端|服务端|接口(?:开发|设计|调用|对接|集成)"),
    "rag_frameworks": ("LangChain/LangGraph/LlamaIndex", r"lang\s*chain|lang\s*graph|llama\s*index"),
    "vector_retrieval": ("向量数据库/向量检索", r"向量(?:数据库|库|检索|搜索|索引|存储)|vector\s*(?:database|search|store)|milvus|faiss|chroma|qdrant|pinecone|weaviate|pgvector"),
    "low_code": ("Dify/Coze/n8n", r"(?<![a-z])(?:dify|coze|n8n)(?![a-z])|扣子"),
    "embedding": ("Embedding/文本向量化", r"embedding|向量化|文本嵌入|嵌入模型"),
    "document_processing": ("文档解析/清洗/分块/OCR", r"文档解析|文档处理|文本解析|数据清洗|文档清洗|数据治理|文档治理|切分|切片|分块|chunk(?:ing)?|(?<![a-z])ocr(?![a-z])|mineru|unstructured"),
    "retrieval_optimization": ("检索优化/混合检索/重排", r"混合检索|多路召回|重排|重排序|rerank|bm25|召回(?:率|质量|优化)|检索(?:优化|效果|质量|精度|准确)|准召"),
    "evaluation": ("评测/幻觉治理", r"评测|效果评估|模型评估|性能评估|质量评估|幻觉|ragas|evaluation|evals"),
    "fine_tuning": ("模型微调/训练适配", r"微调|fine[ -]?tun|(?<![a-z])(?:sft|lora|qlora|peft|dpo|rlhf)(?![a-z])"),
    "deployment": ("部署/容器/推理服务", r"docker|kubernetes|k8s|linux|私有化部署|本地部署|模型部署|推理(?:服务|部署|优化|加速)|vllm|sglang|ollama|tensorrt"),
    "mcp": ("MCP", r"(?<![a-z])mcp(?![a-z])|model\s+context\s+protocol"),
    "knowledge_graph": ("知识图谱/GraphRAG", r"知识图谱|graph\s*rag|neo4j|knowledge\s*graph"),
}
