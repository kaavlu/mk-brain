from datetime import datetime, timezone

from brain.models import Document
from brain.store import queries


def _make_document(**overrides) -> Document:
    defaults = dict(
        id="doc-1",
        source="obsidian",
        path="note.md",
        title="Note",
        content="Hello world",
        tags=["a", "b"],
        frontmatter={"title": "Note"},
        links=["Other Note"],
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        ingested_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return Document(**defaults)


def test_upsert_then_get_by_id_round_trips(conn):
    doc = _make_document()
    queries.upsert_document(conn, doc)

    fetched = queries.get_by_id(conn, "doc-1")

    assert fetched == doc


def test_get_by_id_returns_none_when_missing(conn):
    assert queries.get_by_id(conn, "missing") is None


def test_upsert_document_replaces_existing_row(conn):
    queries.upsert_document(conn, _make_document(title="Old Title"))
    queries.upsert_document(conn, _make_document(title="New Title"))

    fetched = queries.get_by_id(conn, "doc-1")

    assert fetched.title == "New Title"
    count = conn.execute(
        "SELECT COUNT(*) FROM documents WHERE id = 'doc-1'"
    ).fetchone()[0]
    assert count == 1
