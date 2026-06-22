from datetime import date, datetime, timezone

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


def test_search_finds_matching_document_by_content(conn):
    queries.upsert_document(
        conn, _make_document(id="doc-1", title="Alpha", content="The quick brown fox")
    )
    queries.upsert_document(
        conn, _make_document(id="doc-2", title="Beta", content="Nothing relevant here")
    )

    results = queries.search(conn, '"fox"')

    assert [r.id for r in results] == ["doc-1"]
    assert results[0].title == "Alpha"
    assert "fox" in results[0].snippet.lower()


def test_search_filters_by_source(conn):
    queries.upsert_document(
        conn, _make_document(id="doc-1", source="obsidian", content="shared keyword")
    )
    queries.upsert_document(
        conn, _make_document(id="doc-2", source="gdocs", content="shared keyword")
    )

    results = queries.search(conn, '"keyword"', source="gdocs")

    assert [r.id for r in results] == ["doc-2"]


def test_search_filters_by_tags(conn):
    queries.upsert_document(
        conn, _make_document(id="doc-1", tags=["work"], content="shared keyword")
    )
    queries.upsert_document(
        conn, _make_document(id="doc-2", tags=["home"], content="shared keyword")
    )

    results = queries.search(conn, '"keyword"', tags=["home"])

    assert [r.id for r in results] == ["doc-2"]


def test_search_filters_by_multiple_tags_requires_all(conn):
    queries.upsert_document(
        conn, _make_document(id="doc-1", tags=["work"], content="shared keyword")
    )
    queries.upsert_document(
        conn,
        _make_document(id="doc-2", tags=["work", "urgent"], content="shared keyword"),
    )
    queries.upsert_document(
        conn, _make_document(id="doc-3", tags=["urgent"], content="shared keyword")
    )

    results = queries.search(conn, '"keyword"', tags=["work", "urgent"])

    assert [r.id for r in results] == ["doc-2"]


def test_search_respects_limit(conn):
    for i in range(3):
        queries.upsert_document(
            conn, _make_document(id=f"doc-{i}", content="shared keyword")
        )

    results = queries.search(conn, '"keyword"', limit=2)

    assert len(results) == 2


def test_delete_missing_removes_rows_not_in_keep_ids(conn):
    queries.upsert_document(conn, _make_document(id="doc-1", source="obsidian"))
    queries.upsert_document(conn, _make_document(id="doc-2", source="obsidian"))
    queries.upsert_document(conn, _make_document(id="doc-3", source="gdocs"))

    deleted = queries.delete_missing(conn, "obsidian", keep_ids={"doc-1"})

    assert deleted == 1
    assert queries.get_by_id(conn, "doc-2") is None
    assert queries.get_by_id(conn, "doc-1") is not None
    assert queries.get_by_id(conn, "doc-3") is not None


def test_upsert_document_with_date_frontmatter_round_trips_as_string(conn):
    doc = _make_document(frontmatter={"date": date(2024, 1, 15)})

    queries.upsert_document(conn, doc)

    fetched = queries.get_by_id(conn, "doc-1")
    assert fetched.frontmatter == {"date": "2024-01-15"}


def test_list_recent_orders_by_updated_at_descending(conn):
    queries.upsert_document(
        conn, _make_document(id="doc-1", updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    )
    queries.upsert_document(
        conn, _make_document(id="doc-2", updated_at=datetime(2024, 6, 1, tzinfo=timezone.utc))
    )

    results = queries.list_recent(conn, limit=10)

    assert [doc.id for doc in results] == ["doc-2", "doc-1"]
