import csv
import io

import pytest

from job_rag.config import Settings
from job_rag.storage import Database


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", embedding_api_key="",
                    embedding_model="", chat_api_key="", chat_model="", admin_token="test-secret")


@pytest.fixture
def db(settings):
    database = Database(settings)
    database.initialize()
    yield database
    database.engine.dispose()


def row(job_id="one", **changes):
    result = dict(job_id=job_id, title="RAG 应用工程师", company="测试公司", location="广州·天河区·棠下",
                  salary="20-35K·14薪", experience="1-3年", education="本科", url="https://example.com/job/one",
                  description="岗位职责：\n使用 Python 开发 RAG 检索系统。\n要求：熟悉向量数据库与大模型。",
                  status="已获取描述", collected_at="2026-10-23", keywords="Agent")
    result.update(changes)
    return result


def legacy_row(job_id="one", **changes):
    """Pre-2026-10-30 CSV shape, used to simulate an existing database."""
    result = row(job_id=job_id, **changes)
    result.update(address="广州", first_keyword="RAG", keyword_count="1", is_guangzhou="true")
    return result


def csv_bytes(*rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")
