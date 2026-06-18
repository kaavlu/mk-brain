import os
import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.types import EmbeddedResource, ImageContent, TextContent, Tool

from brain.mcp_server import tools
from brain.store.db import get_connection

DEFAULT_DB_PATH = Path.home() / ".brain" / "brain.db"


async def _list_tools(handlers: dict[str, tools.ToolHandler]) -> list[Tool]:
    return [handler.get_tool_description() for handler in handlers.values()]


async def _call_tool(
    handlers: dict[str, tools.ToolHandler],
    name: str,
    arguments: Any,
) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
    if not isinstance(arguments, dict):
        raise RuntimeError("arguments must be dictionary")

    handler = handlers.get(name)
    if not handler:
        raise ValueError(f"Unknown tool: {name}")

    try:
        return handler.run_tool(arguments)
    except tools.ToolError as e:
        raise RuntimeError(str(e)) from e


def build_app(conn: sqlite3.Connection) -> Server:
    app = Server("brain")
    handlers: dict[str, tools.ToolHandler] = {
        h.name: h
        for h in (tools.SearchNotesToolHandler(conn), tools.GetNoteToolHandler(conn))
    }

    app.list_tools()(lambda: _list_tools(handlers))
    app.call_tool()(lambda name, arguments: _call_tool(handlers, name, arguments))

    return app


def resolve_db_path() -> Path:
    return Path(os.environ.get("BRAIN_DB_PATH", DEFAULT_DB_PATH))


async def run() -> None:
    from mcp.server.stdio import stdio_server

    db_path = resolve_db_path()
    if not db_path.exists():
        raise SystemExit(f"Brain store not found at {db_path}. Run 'brain-ingest' first.")

    conn = get_connection(db_path)
    app = build_app(conn)

    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())
