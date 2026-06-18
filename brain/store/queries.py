import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from brain.models import Document


def upsert_document(conn: sqlite3.Connection, doc: Document) -> None:
    conn.execute(
        """
        INSERT INTO documents
            (id, source, path, title, content, tags, frontmatter, links, updated_at, ingested_at)
        VALUES
            (:id, :source, :path, :title, :content, :tags, :frontmatter, :links, :updated_at, :ingested_at)
        ON CONFLICT(id) DO UPDATE SET
            source = excluded.source,
            path = excluded.path,
            title = excluded.title,
            content = excluded.content,
            tags = excluded.tags,
            frontmatter = excluded.frontmatter,
            links = excluded.links,
            updated_at = excluded.updated_at,
            ingested_at = excluded.ingested_at
        """,
        {
            "id": doc.id,
            "source": doc.source,
            "path": doc.path,
            "title": doc.title,
            "content": doc.content,
            "tags": json.dumps(doc.tags, default=str),
            "frontmatter": json.dumps(doc.frontmatter, default=str),
            "links": json.dumps(doc.links, default=str),
            "updated_at": doc.updated_at.isoformat(),
            "ingested_at": doc.ingested_at.isoformat(),
        },
    )
    conn.commit()


def _row_to_document(row: sqlite3.Row) -> Document:
    return Document(
        id=row["id"],
        source=row["source"],
        path=row["path"],
        title=row["title"],
        content=row["content"],
        tags=json.loads(row["tags"]) if row["tags"] else [],
        frontmatter=json.loads(row["frontmatter"]) if row["frontmatter"] else {},
        links=json.loads(row["links"]) if row["links"] else [],
        updated_at=datetime.fromisoformat(row["updated_at"]),
        ingested_at=datetime.fromisoformat(row["ingested_at"]),
    )


def get_by_id(conn: sqlite3.Connection, id: str) -> Document | None:
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (id,)).fetchone()
    return _row_to_document(row) if row else None


@dataclass
class SearchResult:
    id: str
    source: str
    path: str
    title: str
    snippet: str
    score: float


def search(
    conn: sqlite3.Connection,
    fts_query: str,
    source: str | None = None,
    tags: list[str] | None = None,
    limit: int = 10,
) -> list[SearchResult]:
    sql = """
        SELECT
            documents.id AS id,
            documents.source AS source,
            documents.path AS path,
            documents.title AS title,
            snippet(documents_fts, 1, '[', ']', '...', 10) AS snippet,
            bm25(documents_fts) AS score
        FROM documents_fts
        JOIN documents ON documents.rowid = documents_fts.rowid
        WHERE documents_fts MATCH :query
    """
    params: dict = {"query": fts_query}
    if source:
        sql += " AND documents.source = :source"
        params["source"] = source
    if tags:
        tag_clauses = []
        for i, tag in enumerate(tags):
            key = f"tag_{i}"
            tag_clauses.append(f"documents.tags LIKE :{key}")
            params[key] = f'%"{tag}"%'
        sql += " AND (" + " AND ".join(tag_clauses) + ")"
    # bm25() returns lower (more negative) scores for better matches.
    sql += " ORDER BY score LIMIT :limit"
    params["limit"] = limit
    rows = conn.execute(sql, params).fetchall()
    return [
        SearchResult(
            id=row["id"],
            source=row["source"],
            path=row["path"],
            title=row["title"],
            snippet=row["snippet"],
            score=row["score"],
        )
        for row in rows
    ]


def delete_missing(conn: sqlite3.Connection, source: str, keep_ids: set[str]) -> int:
    rows = conn.execute(
        "SELECT id FROM documents WHERE source = ?", (source,)
    ).fetchall()
    to_delete = [row["id"] for row in rows if row["id"] not in keep_ids]
    conn.executemany(
        "DELETE FROM documents WHERE id = ? AND source = ?",
        [(id, source) for id in to_delete],
    )
    conn.commit()
    return len(to_delete)


def list_recent(conn: sqlite3.Connection, limit: int = 10) -> list[Document]:
    rows = conn.execute(
        "SELECT * FROM documents ORDER BY updated_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_row_to_document(row) for row in rows]
