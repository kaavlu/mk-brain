import json
import sqlite3
from collections.abc import Sequence

from mcp.types import EmbeddedResource, ImageContent, TextContent, Tool

from brain.core import search as core_search

TOOL_SEARCH_NOTES = "search_notes"
TOOL_GET_NOTE = "get_note"


class ToolError(Exception):
    pass


class ToolHandler:
    def __init__(self, tool_name: str):
        self.name = tool_name

    def get_tool_description(self) -> Tool:
        raise NotImplementedError()

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        raise NotImplementedError()


class SearchNotesToolHandler(ToolHandler):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__(TOOL_SEARCH_NOTES)
        self.conn = conn

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Search notes by keyword/full-text query, optionally filtered by source or tags.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Text to search for."},
                    "source": {
                        "type": "string",
                        "description": "Restrict results to this source (e.g. 'obsidian').",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Restrict results to notes carrying all of these tags.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "query" not in args:
            raise ToolError("query argument missing in arguments")

        try:
            results = core_search.search_notes(
                self.conn,
                args["query"],
                source=args.get("source"),
                tags=args.get("tags"),
                limit=args.get("limit", 10),
            )
        except core_search.BrainError as e:
            raise ToolError(str(e)) from e

        return [
            TextContent(
                type="text",
                text=json.dumps(
                    [
                        {
                            "id": r.id,
                            "source": r.source,
                            "path": r.path,
                            "title": r.title,
                            "snippet": r.snippet,
                            "score": r.score,
                        }
                        for r in results
                    ],
                    indent=2,
                ),
            )
        ]


class GetNoteToolHandler(ToolHandler):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__(TOOL_GET_NOTE)
        self.conn = conn

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Return the full content of a specific document by id.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Document id, as returned by search_notes.",
                    },
                },
                "required": ["id"],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "id" not in args:
            raise ToolError("id argument missing in arguments")

        try:
            doc = core_search.get_note(self.conn, args["id"])
        except core_search.BrainError as e:
            raise ToolError(str(e)) from e

        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "id": doc.id,
                        "source": doc.source,
                        "path": doc.path,
                        "title": doc.title,
                        "content": doc.content,
                        "tags": doc.tags,
                        "frontmatter": doc.frontmatter,
                        "links": doc.links,
                        "updated_at": doc.updated_at.isoformat(),
                        "ingested_at": doc.ingested_at.isoformat(),
                    },
                    indent=2,
                ),
            )
        ]
