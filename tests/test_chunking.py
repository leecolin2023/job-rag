from dataclasses import replace

import pytest
from sqlalchemy import inspect, text

from job_rag.chunking import Budget, build_documents, condition_level, parse_sections
from job_rag.storage import Chunk, Database
from job_rag.preprocessing.importer import import_csv
from job_rag.indexing.worker import run_index_tasks
from job_rag.chunking.legacy import legacy_documents

from conftest import csv_bytes, row


def test_heading_variants_and_inline_content():
    source = "前言。\n【岗位\n职责】\n1.开发系统。\n## 任职要求：1.熟悉Python。\n三、加分项：有RAG经验。"
    sections = parse_sections(source)
    assert [section.section_type for section in sections] == ["unknown", "responsibilities", "requirements", "preferred"]
    assert source[sections[-1].start:sections[-1].end] == "有RAG经验。"
    assert source[sections[1].heading_start:sections[1].heading_end] == "【岗位\n职责】"


def test_no_false_heading_inside_a_sentence():
    sections = parse_sections("负责更新岗位职责文档，以及任职要求字段。\n不是章节。")
    assert len(sections) == 1
    assert sections[0].section_type == "unknown"


def test_crlf_empty_heading_does_not_become_standalone_chunk():
    docs = build_documents(row(description="岗位职责\r\n任职要求：\r\n1.Python或者Java满足其一。\r\n"))
    assert len(docs) == 1
    assert docs[0].details["section_type"] == "requirements"
    assert docs[0].details["requirement_level"] == "mixed"
    assert "Python或者Java" in docs[0].details["raw_text"]


def test_decorated_headers_keep_preferred_scope():
    source = "▍你会做什么\n开发平台。\n▍我们希望你\n1.熟悉Python。\n▍加分项（有就聊，没有也别划走）\n1.玩过vLLM。"
    docs = build_documents(row(description=source))
    assert any(doc.details["section_type"] == "preferred" and "vLLM" in doc.text for doc in docs)


@pytest.mark.parametrize("text,section,expected", [
    ("熟悉Python。", "requirements", "required"),
    ("有RAG经验者优先。", "requirements", "preferred"),
    ("必须掌握Python，同时RAG经验优先。", "requirements", "mixed"),
    ("熟悉Python，RAG经验优先。", "requirements", "mixed"),
    ("本科以上，优秀者可放宽。", "requirements", "mixed"),
    ("Python或者Java满足其一。", "requirements", "mixed"),
    ("不要求算法研发经验。", "requirements", "not_required"),
    ("not required", "requirements", "not_required"),
    ("不要求算法研发，但需具备脚本能力。", "requirements", "mixed"),
    ("必须优先保障服务稳定。", "responsibilities", "unspecified"),
    ("开源贡献。", "preferred", "preferred"),
    ("上下文未知。", "unknown", "unspecified"),
])
def test_condition_levels(text, section, expected):
    assert condition_level(text, section) == expected


def test_no_cross_section_or_condition_and_preserve_source():
    original = row(description="岗位职责：\n1.构建知识库。\n任职要求：\n1.必须掌握Python。\n2.有RAG经验者优先。\n加分项：\n1.熟悉Neo4j。")
    docs = build_documents(original)
    assert {doc.details["requirement_level"] for doc in docs} >= {"required", "preferred"}
    for doc in docs:
        detail = doc.details
        assert original["description"][detail["source_start"]:detail["source_end"]] == detail["raw_text"]
        if "有RAG经验者优先" in detail["raw_text"]:
            assert detail["requirement_level"] == "preferred"
            assert "必须掌握Python" not in detail["raw_text"]
    assert "薪资：" not in "".join(doc.text for doc in docs)


def test_compact_and_typed_same_boundaries():
    record = row(description="岗位职责：\n1.开发系统。\n任职要求：\n1.必须掌握Python。\n2.有RAG经验者优先。")
    compact = build_documents(record, "section_compact", size=150)
    typed = build_documents(record, "section_typed", size=150)
    assert [(d.details["source_start"], d.details["source_end"]) for d in compact] == [(d.details["source_start"], d.details["source_end"]) for d in typed]


def test_legacy_control_is_exact_original():
    record = row(description="Python RAG\n" * 500)
    assert [doc.text for doc in build_documents(record, "legacy")] == legacy_documents(record)
    assert [doc.details["raw_text"] for doc in build_documents(record, "legacy")] == [doc.details["raw_text"] for doc in build_documents(record, "fixed_compact")]


def test_hard_split_no_loss_and_inherits_item_scope():
    source = "加分项：\n1." + "超长技术内容" * 1000
    docs = build_documents(row(description=source), size=160)
    assert len(docs) > 10
    assert all(len(doc.text) <= 160 for doc in docs)
    assert all(doc.details["section_type"] == "preferred" for doc in docs)
    assert any(doc.details["hard_split"] for doc in docs)
    sections = parse_sections(source)
    assert "".join(doc.details["raw_text"] for doc in docs) == source[sections[0].start:]
    assert len({item["continuation_id"] for doc in docs for item in doc.details["item_spans"]}) == 1


def test_utf8_budget_is_not_mislabeled_as_tokens():
    docs = build_documents(row(description="任职要求：\n1." + "中文条件" * 100), size=300, budget_kind="utf8_bytes")
    assert all(len(doc.text.encode()) <= 300 and doc.details["budget_unit"] == "utf8_bytes" for doc in docs)
    with pytest.raises(ValueError, match="tokenizer"):
        Budget("tokens")


def test_salary_update_reuses_embeddings_and_keeps_section_metadata(db, settings, monkeypatch):
    configured = replace(settings, embedding_api_key="dummy", embedding_model="test", embedding_dimensions=2)
    calls = []

    def vectors(_, texts):
        calls.append(texts)
        return [[1., 0.] for _ in texts]

    monkeypatch.setattr("job_rag.indexing.worker.embed", vectors)
    import_csv(db, configured, csv_bytes(row()))
    run_index_tasks(db, configured)
    import_csv(db, configured, csv_bytes(row(salary="25-40K")))
    run_index_tasks(db, configured)
    assert len(calls) == 1
    with db.session() as session:
        chunks = session.query(Chunk).all()
        assert chunks and all(chunk.details["parser_version"] for chunk in chunks)


def test_explicit_additive_migration(settings):
    db = Database(settings)
    with db.engine.begin() as connection:
        connection.execute(text("CREATE TABLE chunks (id INTEGER PRIMARY KEY, job_key VARCHAR, version INTEGER, ordinal INTEGER, text TEXT, embedding JSON)"))
        connection.execute(text("INSERT INTO chunks VALUES (1, 'boss:old', 1, 0, 'old source', NULL)"))
    with pytest.raises(ValueError, match="migrate"):
        db.initialize()
    assert db.migrate()["reindex_required"]
    assert db.migrate()["ok"]
    assert "details" in {column["name"] for column in inspect(db.engine).get_columns("chunks")}
    with db.session() as session:
        assert session.get(Chunk, 1).text == "old source"
        assert session.get(Chunk, 1).details is None
        assert session.scalar(text("SELECT COUNT(*) FROM schema_migrations")) == 1
    db.engine.dispose()


def test_signature_includes_strategy_budget_and_parser(settings):
    assert settings.index_signature != replace(settings, chunking_strategy="legacy").index_signature
    assert settings.index_signature != replace(settings, chunk_size=600).index_signature


def test_parser_failure_is_a_retryable_index_task(db, settings):
    configured = replace(settings, chunk_size=1)
    import_csv(db, configured, csv_bytes(row()))
    result = run_index_tasks(db, configured)
    assert result["failed"] == 1
    from job_rag.storage import IndexTask
    with db.session() as session:
        task = session.query(IndexTask).one()
        assert task.state == "failed"
        assert task.error == "ValueError"
