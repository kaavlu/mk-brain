from datetime import datetime, timezone

import pytest

from brain.core.search import BrainError, get_note, search_notes
from brain.models import Document
from brain.store import queries


def _doc(id, content="hello world", tags=None, source="obsidian"):
    return Document(
        id=id,
        source=source,
        path=f"{id}.md",
        title=id,
        content=content,
        tags=tags or [],
        frontmatter={},
        links=[],
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        ingested_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def test_search_notes_returns_matches(conn):
    queries.upsert_document(conn, _doc("a", content="alpha beta gamma"))

    results = search_notes(conn, "alpha")

    assert [r.id for r in results] == ["a"]


def test_search_notes_rejects_empty_query(conn):
    with pytest.raises(BrainError, match="query must not be empty"):
        search_notes(conn, "")
    with pytest.raises(BrainError, match="query must not be empty"):
        search_notes(conn, "   ")


def test_search_notes_escapes_double_quotes_without_sql_error(conn):
    queries.upsert_document(conn, _doc("a", content='He said "hello" to me'))

    results = search_notes(conn, 'said "hello" to')

    assert [r.id for r in results] == ["a"]


def test_get_note_returns_document(conn):
    queries.upsert_document(conn, _doc("a"))

    doc = get_note(conn, "a")

    assert doc.id == "a"


def test_get_note_raises_for_unknown_id(conn):
    with pytest.raises(BrainError, match="No document with id missing"):
        get_note(conn, "missing")
