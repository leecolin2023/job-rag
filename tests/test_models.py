from dataclasses import replace

import httpx
import pytest
from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, select
from sqlalchemy.dialects import postgresql

from job_rag.db import Chunk
from job_rag.models import embed


def test_pgvector_query_compiles():
    statement = select(Chunk.id).order_by(cast(Chunk.embedding, Vector()).cosine_distance([1., 0.]))
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "<=>" in compiled
    assert "VECTOR" in compiled


@pytest.mark.parametrize("data", [
    [{"index": 0, "embedding": [1.]}],
    [{"index": 0, "embedding": [0., 0.]}],
    [{"index": 0, "embedding": [1., float("nan")]}],
    [{"index": 1, "embedding": [1., 0.]}],
    [],
])
def test_embedding_validates_response(settings, monkeypatch, data):
    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def post(self, url, **kwargs):
            # httpx JSON encoding rejects NaN, so the fake response supplies data directly.
            class Response:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"data": data}
            return Response()

    monkeypatch.setattr(httpx, "Client", Client)
    configured = replace(settings, embedding_api_key="dummy", embedding_model="mock", embedding_dimensions=2)
    with pytest.raises(ValueError):
        embed(configured, ["test"])
