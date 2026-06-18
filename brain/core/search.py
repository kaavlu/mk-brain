import sqlite3

from brain.models import Document
from brain.store import queries
from brain.store.queries import SearchResult


class BrainError(Exception):
    pass


def search_notes(
    conn: sqlite3.Connection,
    query: str,
    source: str | None = None,
    tags: list[str] | None = None,
    limit: int = 10,
) -> list[SearchResult]:
    if not query or not query.strip():
        raise BrainError("query must not be empty")
    escaped = _escape_fts5(query)
    return queries.search(conn, escaped, source=source, tags=tags, limit=limit)


def get_note(conn: sqlite3.Connection, id: str) -> Document:
    doc = queries.get_by_id(conn, id)
    if doc is None:
        raise BrainError(f"No document with id {id}")
    return doc


def _escape_fts5(query: str) -> str:
    return '"' + query.replace('"', '""') + '"'
