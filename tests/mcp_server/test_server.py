from pathlib import Path

import pytest

from brain.mcp_server.server import (
    DEFAULT_DB_PATH,
    _call_tool,
    _list_tools,
    build_app,
    resolve_db_path,
    run,
)
from brain.mcp_server.tools import GetNoteToolHandler, SearchNotesToolHandler


def test_build_app_returns_server_named_brain(conn):
    app = build_app(conn)
    assert app.name == "brain"


async def test_list_tools_returns_search_notes_and_get_note(conn):
    handlers = {
        "search_notes": SearchNotesToolHandler(conn),
        "get_note": GetNoteToolHandler(conn),
    }

    result = await _list_tools(handlers)

    assert {t.name for t in result} == {"search_notes", "get_note"}


async def test_call_tool_rejects_non_dict_arguments(conn):
    handlers = {"search_notes": SearchNotesToolHandler(conn)}

    with pytest.raises(RuntimeError, match="arguments must be dictionary"):
        await _call_tool(handlers, "search_notes", None)


async def test_call_tool_rejects_unknown_tool(conn):
    with pytest.raises(ValueError, match="Unknown tool"):
        await _call_tool({}, "missing", {})


async def test_call_tool_dispatches_to_handler(conn):
    handlers = {"search_notes": SearchNotesToolHandler(conn)}

    result = await _call_tool(handlers, "search_notes", {"query": "x"})

    assert result[0].type == "text"


async def test_call_tool_wraps_tool_error_as_runtime_error(conn):
    handlers = {"get_note": GetNoteToolHandler(conn)}

    with pytest.raises(RuntimeError, match="No document with id missing"):
        await _call_tool(handlers, "get_note", {"id": "missing"})


def test_resolve_db_path_uses_env_var(monkeypatch):
    monkeypatch.setenv("BRAIN_DB_PATH", "/tmp/custom-brain.db")
    assert resolve_db_path() == Path("/tmp/custom-brain.db")


def test_resolve_db_path_defaults_to_home_brain_db(monkeypatch):
    monkeypatch.delenv("BRAIN_DB_PATH", raising=False)
    assert resolve_db_path() == DEFAULT_DB_PATH


async def test_run_fails_fast_when_db_missing(monkeypatch, tmp_path):
    missing = tmp_path / "missing.db"
    monkeypatch.setenv("BRAIN_DB_PATH", str(missing))

    with pytest.raises(SystemExit, match="Run 'brain-ingest' first"):
        await run()
