import json
import sqlite3
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
            "tags": json.dumps(doc.tags),
            "frontmatter": json.dumps(doc.frontmatter),
            "links": json.dumps(doc.links),
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
