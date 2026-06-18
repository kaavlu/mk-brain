import json
from datetime import datetime, timezone

import pytest

from brain.mcp_server.tools import GetNoteToolHandler, SearchNotesToolHandler, ToolError
from brain.models import Document
from brain.store import queries


def _doc(id, content="hello world"):
    return Document(
        id=id,
        source="obsidian",
        path=f"{id}.md",
        title=id,
        content=content,
        tags=["x"],
        frontmatter={},
        links=[],
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        ingested_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def test_search_notes_tool_handler_returns_matches(conn):
    queries.upsert_document(conn, _doc("a", content="alpha beta"))
    handler = SearchNotesToolHandler(conn)

    result = handler.run_tool({"query": "alpha"})

    payload = json.loads(result[0].text)
    assert [r["id"] for r in payload] == ["a"]


def test_search_notes_tool_handler_requires_query(conn):
    handler = SearchNotesToolHandler(conn)

    with pytest.raises(ToolError, match="query"):
        handler.run_tool({})


def test_search_notes_tool_handler_wraps_empty_query_as_tool_error(conn):
    handler = SearchNotesToolHandler(conn)

    with pytest.raises(ToolError, match="query must not be empty"):
        handler.run_tool({"query": "   "})


def test_get_note_tool_handler_returns_full_document(conn):
    queries.upsert_document(conn, _doc("a"))
    handler = GetNoteToolHandler(conn)

    result = handler.run_tool({"id": "a"})

    payload = json.loads(result[0].text)
    assert payload["id"] == "a"
    assert payload["content"] == "hello world"


def test_get_note_tool_handler_requires_id(conn):
    handler = GetNoteToolHandler(conn)

    with pytest.raises(ToolError, match="id"):
        handler.run_tool({})


def test_get_note_tool_handler_wraps_unknown_id_as_tool_error(conn):
    handler = GetNoteToolHandler(conn)

    with pytest.raises(ToolError, match="No document with id missing"):
        handler.run_tool({"id": "missing"})
