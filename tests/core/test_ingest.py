from datetime import datetime, timezone

from brain.core.ingest import ingest_source
from brain.models import Document
from brain.store import queries


def _doc(id, content="body", source="fake"):
    return Document(
        id=id,
        source=source,
        path=f"{id}.md",
        title=id,
        content=content,
        tags=[],
        frontmatter={},
        links=[],
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        ingested_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


class _FakeConnector:
    def __init__(self, docs):
        self._docs = docs

    def iter_documents(self):
        return iter(self._docs)


def test_ingest_source_upserts_all_documents(conn):
    connector = _FakeConnector([_doc("a"), _doc("b")])

    result = ingest_source(conn, "fake", connector)

    assert result.upserted == 2
    assert result.skipped == 0
    assert queries.get_by_id(conn, "a") is not None
    assert queries.get_by_id(conn, "b") is not None


def test_ingest_source_skips_document_that_fails_to_upsert(conn):
    connector = _FakeConnector([_doc("a"), _doc("b", content=None), _doc("c")])

    result = ingest_source(conn, "fake", connector)

    assert result.upserted == 2
    assert result.skipped == 1
    assert queries.get_by_id(conn, "a") is not None
    assert queries.get_by_id(conn, "b") is None
    assert queries.get_by_id(conn, "c") is not None


def test_ingest_source_deletes_rows_from_same_source_not_seen_this_run(conn):
    queries.upsert_document(conn, _doc("stale"))

    connector = _FakeConnector([_doc("a")])
    result = ingest_source(conn, "fake", connector)

    assert result.deleted == 1
    assert queries.get_by_id(conn, "stale") is None
    assert queries.get_by_id(conn, "a") is not None


def test_ingest_source_does_not_delete_rows_from_other_sources(conn):
    queries.upsert_document(conn, _doc("other-source-doc", source="other"))

    connector = _FakeConnector([_doc("a")])
    ingest_source(conn, "fake", connector)

    assert queries.get_by_id(conn, "other-source-doc") is not None


def test_ingest_source_keeps_previously_ingested_document_that_fails_to_reupsert(conn):
    queries.upsert_document(conn, _doc("a"))

    connector = _FakeConnector([_doc("a", content=None)])
    result = ingest_source(conn, "fake", connector)

    assert result.skipped == 1
    assert result.upserted == 0
    assert result.deleted == 0
    assert queries.get_by_id(conn, "a") is not None
