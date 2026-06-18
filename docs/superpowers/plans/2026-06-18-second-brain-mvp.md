# Second Brain MCP MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only, local-first "Second Brain" MCP server that exposes keyword/full-text search over an Obsidian vault to Claude Code via two MCP tools (`search_notes`, `get_note`), backed by a single SQLite+FTS5 store, with a separate manual CLI ingestion pipeline.

**Architecture:** A layered `brain` package (`models` → `store` → `core` → `connectors`/`mcp_server`) shared by two entry points: `brain-serve` (long-lived stdio MCP server, read-only) and `brain-ingest` (short-lived CLI, write-only, full re-sync). The MCP server is a thin adapter over `mcp.server.Server` mirroring the reference `mcp-obsidian` project's `ToolHandler` class pattern; `brain/core` owns query/ingest business logic; `brain/store` owns SQLite schema and queries; `brain/connectors/obsidian.py` reads the vault directly from disk.

**Tech Stack:** Python >=3.11, `mcp>=1.1.0` (low-level `Server` API, mirroring `mcp-obsidian`), `python-frontmatter>=1.1.0` for YAML frontmatter parsing, stdlib `sqlite3` with FTS5, `argparse` for CLI entry points, `pytest`/`pytest-asyncio` for tests, managed with `uv`.

## Global Constraints

- Python `>=3.11` (per `pyproject.toml` `requires-python`).
- MVP scope is read-only keyword/full-text search only — no semantic search, embeddings, or custom ranking beyond FTS5's built-in `bm25()`.
- No write actions (append/patch/delete notes) — explicitly deferred.
- Ingestion is a manual, full-resync CLI command only — no file watcher, no incremental diffing.
- Obsidian vault is read directly from disk — no dependency on the Local REST API plugin.
- Single `brain` package, layered internally (`store` / `core` / `connectors` / `mcp_server`) — no flat scripts, no separate ingest/serve projects.
- `documents_fts` is an external-content FTS5 table (`content='documents', content_rowid='rowid'`) kept in sync via triggers — no dual-write logic in application code.
- No mocking of SQLite in tests — every test hits a real (`:memory:` or temp-file) database.
- Per-file connector errors (malformed YAML, bad encoding) are caught and skipped, never abort an ingestion run.
- `~/.brain/brain.db` is the default store location, overridable via `BRAIN_DB_PATH` env var.

---

## Task 1: Project Scaffolding & Document Model

**Files:**
- Create: `pyproject.toml`
- Create: `brain/__init__.py`
- Create: `brain/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `brain.models.Document` dataclass with fields `id: str, source: str, path: str, title: str, content: str, tags: list[str], frontmatter: dict, links: list[str], updated_at: datetime, ingested_at: datetime` — every later task constructs `Document` instances with exactly these fields, in this order, no defaults.

- [ ] **Step 1: Install `uv` (package/dependency manager for this project)**

Run: `brew install uv`
Expected: installs successfully; `uv --version` prints a version string afterward.

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "brain"
version = "0.1.0"
description = "Local-first personal Second Brain MCP server"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.1.0",
    "python-frontmatter>=1.1.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["brain", "cli"]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
asyncio_mode = "auto"

[project.scripts]
brain-ingest = "cli.ingest:main"
brain-serve = "cli.serve:main"
```

- [ ] **Step 3: Create empty package marker**

Create `brain/__init__.py` with empty content (0 bytes).

- [ ] **Step 4: Write the failing test for `Document`**

Create `tests/test_models.py`:

```python
from datetime import datetime, timezone

from brain.models import Document


def test_document_holds_all_fields():
    doc = Document(
        id="abc123",
        source="obsidian",
        path="notes/a.md",
        title="A",
        content="body",
        tags=["x"],
        frontmatter={"title": "A"},
        links=["B"],
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        ingested_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
    )

    assert doc.id == "abc123"
    assert doc.source == "obsidian"
    assert doc.path == "notes/a.md"
    assert doc.title == "A"
    assert doc.content == "body"
    assert doc.tags == ["x"]
    assert doc.frontmatter == {"title": "A"}
    assert doc.links == ["B"]
    assert doc.updated_at == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert doc.ingested_at == datetime(2024, 1, 2, tzinfo=timezone.utc)
```

- [ ] **Step 5: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brain.models'` (dependencies install automatically on first `uv run`).

- [ ] **Step 6: Write minimal implementation**

Create `brain/models.py`:

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Document:
    id: str
    source: str
    path: str
    title: str
    content: str
    tags: list[str]
    frontmatter: dict
    links: list[str]
    updated_at: datetime
    ingested_at: datetime
```

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py -v`
Expected: `1 passed`

- [ ] **Step 8: Commit**

```bash
git init
git add pyproject.toml brain/__init__.py brain/models.py tests/test_models.py
git commit -m "feat: scaffold project and add Document model"
```

---

## Task 2: Store Schema & Connection Management

**Files:**
- Create: `brain/store/__init__.py`
- Create: `brain/store/schema.sql`
- Create: `brain/store/db.py`
- Test: `tests/store/test_db.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `brain.store.db.get_connection(db_path: str | Path) -> sqlite3.Connection` — opens (creating parent dirs and schema if needed) a connection with `row_factory = sqlite3.Row`. Later tasks use this for every DB access, including `:memory:` for tests.

- [ ] **Step 1: Create package marker**

Create `brain/store/__init__.py` with empty content.

- [ ] **Step 2: Write the failing test**

Create `tests/store/test_db.py`:

```python
from brain.store.db import get_connection


def test_get_connection_creates_documents_and_fts_tables():
    conn = get_connection(":memory:")

    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }

    assert "documents" in tables
    assert "documents_fts" in tables


def test_get_connection_is_idempotent_when_called_twice(tmp_path):
    db_path = tmp_path / "brain.db"

    conn1 = get_connection(db_path)
    conn1.close()
    conn2 = get_connection(db_path)

    tables = {
        row[0]
        for row in conn2.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert "documents" in tables
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/store/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brain.store.db'`

- [ ] **Step 4: Write `schema.sql`**

Create `brain/store/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    path TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT,
    frontmatter TEXT,
    links TEXT,
    updated_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title, content, tags,
    content='documents', content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, title, content, tags)
    VALUES (new.rowid, new.title, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, content, tags)
    VALUES ('delete', old.rowid, old.title, old.content, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, content, tags)
    VALUES ('delete', old.rowid, old.title, old.content, old.tags);
    INSERT INTO documents_fts(rowid, title, content, tags)
    VALUES (new.rowid, new.title, new.content, new.tags);
END;
```

- [ ] **Step 5: Write minimal implementation**

Create `brain/store/db.py`:

```python
import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_PATH.read_text())
    return conn
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/store/test_db.py -v`
Expected: `2 passed`

- [ ] **Step 7: Commit**

```bash
git add brain/store/__init__.py brain/store/schema.sql brain/store/db.py tests/store/test_db.py
git commit -m "feat: add SQLite+FTS5 schema and connection management"
```

---

## Task 3: Store Queries — `upsert_document` & `get_by_id`

**Files:**
- Create: `brain/store/queries.py`
- Create: `tests/conftest.py`
- Test: `tests/store/test_queries.py`

**Interfaces:**
- Consumes: `brain.models.Document` (Task 1), `brain.store.db.get_connection` (Task 2).
- Produces: `upsert_document(conn, doc: Document) -> None`, `get_by_id(conn, id: str) -> Document | None`, `_row_to_document(row) -> Document` (internal helper reused by later store functions). Also produces the `conn` pytest fixture in `tests/conftest.py`, reused by every later test file.

- [ ] **Step 1: Create the shared `conn` fixture**

Create `tests/conftest.py`:

```python
import pytest

from brain.store.db import get_connection


@pytest.fixture
def conn():
    connection = get_connection(":memory:")
    yield connection
    connection.close()
```

- [ ] **Step 2: Write the failing test**

Create `tests/store/test_queries.py`:

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/store/test_queries.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brain.store.queries'`

- [ ] **Step 4: Write minimal implementation**

Create `brain/store/queries.py`:

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/store/test_queries.py -v`
Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add brain/store/queries.py tests/conftest.py tests/store/test_queries.py
git commit -m "feat: add upsert_document and get_by_id store queries"
```

---

## Task 4: Store Queries — `search`

**Files:**
- Modify: `brain/store/queries.py`
- Modify: `tests/store/test_queries.py`

**Interfaces:**
- Consumes: `upsert_document`, `_row_to_document` pattern (Task 3).
- Produces: `SearchResult` dataclass (`id, source, path, title, snippet, score`) and `search(conn, fts_query: str, source: str | None = None, tags: list[str] | None = None, limit: int = 10) -> list[SearchResult]`. Later tasks (`core.search.search_notes`, MCP tool handlers) call this exact signature.

- [ ] **Step 1: Write the failing tests**

Append to `tests/store/test_queries.py`:

```python
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


def test_search_respects_limit(conn):
    for i in range(3):
        queries.upsert_document(
            conn, _make_document(id=f"doc-{i}", content="shared keyword")
        )

    results = queries.search(conn, '"keyword"', limit=2)

    assert len(results) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/store/test_queries.py -v`
Expected: FAIL with `AttributeError: module 'brain.store.queries' has no attribute 'search'`

- [ ] **Step 3: Write minimal implementation**

Append to `brain/store/queries.py` (add `from dataclasses import dataclass` to the existing imports at the top of the file):

```python
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
        sql += " AND (" + " OR ".join(tag_clauses) + ")"
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/store/test_queries.py -v`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add brain/store/queries.py tests/store/test_queries.py
git commit -m "feat: add FTS5-backed search query with source/tag filters"
```

---

## Task 5: Store Queries — `delete_missing` & `list_recent`

**Files:**
- Modify: `brain/store/queries.py`
- Modify: `tests/store/test_queries.py`

**Interfaces:**
- Consumes: `upsert_document`, `get_by_id`, `_row_to_document` (Tasks 3-4).
- Produces: `delete_missing(conn, source: str, keep_ids: set[str]) -> int`, `list_recent(conn, limit: int = 10) -> list[Document]`. `delete_missing` is consumed by `core.ingest.ingest_source` in Task 10.

- [ ] **Step 1: Write the failing tests**

Append to `tests/store/test_queries.py`:

```python
def test_delete_missing_removes_rows_not_in_keep_ids(conn):
    queries.upsert_document(conn, _make_document(id="doc-1", source="obsidian"))
    queries.upsert_document(conn, _make_document(id="doc-2", source="obsidian"))
    queries.upsert_document(conn, _make_document(id="doc-3", source="gdocs"))

    deleted = queries.delete_missing(conn, "obsidian", keep_ids={"doc-1"})

    assert deleted == 1
    assert queries.get_by_id(conn, "doc-2") is None
    assert queries.get_by_id(conn, "doc-1") is not None
    assert queries.get_by_id(conn, "doc-3") is not None


def test_list_recent_orders_by_updated_at_descending(conn):
    queries.upsert_document(
        conn, _make_document(id="doc-1", updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    )
    queries.upsert_document(
        conn, _make_document(id="doc-2", updated_at=datetime(2024, 6, 1, tzinfo=timezone.utc))
    )

    results = queries.list_recent(conn, limit=10)

    assert [doc.id for doc in results] == ["doc-2", "doc-1"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/store/test_queries.py -v`
Expected: FAIL with `AttributeError: module 'brain.store.queries' has no attribute 'delete_missing'`

- [ ] **Step 3: Write minimal implementation**

Append to `brain/store/queries.py`:

```python
def delete_missing(conn: sqlite3.Connection, source: str, keep_ids: set[str]) -> int:
    rows = conn.execute(
        "SELECT id FROM documents WHERE source = ?", (source,)
    ).fetchall()
    to_delete = [row["id"] for row in rows if row["id"] not in keep_ids]
    conn.executemany(
        "DELETE FROM documents WHERE id = ?", [(id,) for id in to_delete]
    )
    conn.commit()
    return len(to_delete)


def list_recent(conn: sqlite3.Connection, limit: int = 10) -> list[Document]:
    rows = conn.execute(
        "SELECT * FROM documents ORDER BY updated_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_row_to_document(row) for row in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/store/test_queries.py -v`
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add brain/store/queries.py tests/store/test_queries.py
git commit -m "feat: add delete_missing re-sync and list_recent store queries"
```

---

## Task 6: Connector Base Protocol

**Files:**
- Create: `brain/connectors/__init__.py`
- Create: `brain/connectors/base.py`
- Test: `tests/connectors/test_base.py`

**Interfaces:**
- Consumes: `brain.models.Document` (Task 1).
- Produces: `Connector` runtime-checkable `Protocol` with `iter_documents(self) -> Iterator[Document]`. Consumed by `ObsidianConnector` (Task 7) and `core.ingest.ingest_source` (Task 10).

- [ ] **Step 1: Create package marker**

Create `brain/connectors/__init__.py` with empty content.

- [ ] **Step 2: Write the failing test**

Create `tests/connectors/test_base.py`:

```python
from brain.connectors.base import Connector


class _FakeConnector:
    def iter_documents(self):
        return iter([])


def test_fake_connector_satisfies_protocol():
    assert isinstance(_FakeConnector(), Connector)


def test_object_without_method_does_not_satisfy_protocol():
    assert not isinstance(object(), Connector)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/connectors/test_base.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brain.connectors.base'`

- [ ] **Step 4: Write minimal implementation**

Create `brain/connectors/base.py`:

```python
from typing import Iterator, Protocol, runtime_checkable

from brain.models import Document


@runtime_checkable
class Connector(Protocol):
    def iter_documents(self) -> Iterator[Document]:
        ...
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/connectors/test_base.py -v`
Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add brain/connectors/__init__.py brain/connectors/base.py tests/connectors/test_base.py
git commit -m "feat: add Connector protocol"
```

---

## Task 7: Obsidian Connector — Walk, Frontmatter, Links

**Files:**
- Create: `brain/connectors/obsidian.py`
- Create: `tests/connectors/test_obsidian.py`
- Modify: `tests/conftest.py`
- Create: `tests/fixtures/vault/note1.md`
- Create: `tests/fixtures/vault/empty_frontmatter.md`

**Interfaces:**
- Consumes: `brain.models.Document` (Task 1), `brain.connectors.base.Connector` (Task 6).
- Produces: `ObsidianConnector(vault_path: Path)` with `.iter_documents() -> Iterator[Document]`. Tags at this stage come from frontmatter only (inline merge added in Task 8); error isolation and directory skipping added in Task 9.

- [ ] **Step 1: Add the shared fixture-vault path fixture**

Append to `tests/conftest.py`:

```python
from pathlib import Path

FIXTURE_VAULT = Path(__file__).parent / "fixtures" / "vault"


@pytest.fixture
def fixture_vault_path() -> Path:
    return FIXTURE_VAULT
```

- [ ] **Step 2: Create fixture vault files**

Create `tests/fixtures/vault/note1.md`:

```
---
title: Note One
tags: [project]
---
This is the body with an inline #work tag and a link to [[Note Two]].
```

Create `tests/fixtures/vault/empty_frontmatter.md`:

```
No frontmatter here, just a plain note with an inline #note tag.
```

- [ ] **Step 3: Write the failing test**

Create `tests/connectors/test_obsidian.py`:

```python
from datetime import datetime, timezone

from brain.connectors.obsidian import ObsidianConnector


def _by_path(docs, path):
    return next(d for d in docs if d.path == path)


def test_iter_documents_parses_frontmatter_title_links_and_id(fixture_vault_path):
    docs = list(ObsidianConnector(fixture_vault_path).iter_documents())

    doc = _by_path(docs, "note1.md")
    stat = (fixture_vault_path / "note1.md").stat()

    assert doc.id == "d34256f07c2bc72744fe80796e32eeb8ab7229140eb86d0e37ccbd98a0aa149d"
    assert doc.source == "obsidian"
    assert doc.title == "Note One"
    assert doc.content.strip() == (
        "This is the body with an inline #work tag and a link to [[Note Two]]."
    )
    assert doc.frontmatter == {"title": "Note One", "tags": ["project"]}
    assert doc.links == ["Note Two"]
    assert doc.updated_at == datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    assert (datetime.now(timezone.utc) - doc.ingested_at).total_seconds() < 5


def test_iter_documents_falls_back_to_filename_stem_for_title(fixture_vault_path):
    docs = list(ObsidianConnector(fixture_vault_path).iter_documents())

    doc = _by_path(docs, "empty_frontmatter.md")

    assert doc.id == "e3bde0a353cbf05f1130f98114fd3251801b328f92210143827c3348edb7e1ac"
    assert doc.title == "empty_frontmatter"
    assert doc.content.strip() == (
        "No frontmatter here, just a plain note with an inline #note tag."
    )
    assert doc.frontmatter == {}
    assert doc.links == []
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/connectors/test_obsidian.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brain.connectors.obsidian'`

- [ ] **Step 5: Write minimal implementation**

Create `brain/connectors/obsidian.py`:

```python
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import frontmatter

from brain.models import Document

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")


class ObsidianConnector:
    def __init__(self, vault_path: Path):
        self.vault_path = Path(vault_path)

    def iter_documents(self) -> Iterator[Document]:
        for path in sorted(self.vault_path.rglob("*.md")):
            relative = path.relative_to(self.vault_path)
            yield self._parse_file(path, relative)

    def _parse_file(self, path: Path, relative: Path) -> Document:
        raw = path.read_text(encoding="utf-8")
        post = frontmatter.loads(raw)
        body = post.content
        fm_tags = post.metadata.get("tags") or []
        if isinstance(fm_tags, str):
            fm_tags = [fm_tags]
        tags = sorted(set(fm_tags))
        links = _extract_wikilinks(body)
        title = post.metadata.get("title") or path.stem
        stat = path.stat()
        doc_id = hashlib.sha256(
            f"obsidian:{relative.as_posix()}".encode()
        ).hexdigest()
        return Document(
            id=doc_id,
            source="obsidian",
            path=relative.as_posix(),
            title=title,
            content=body,
            tags=tags,
            frontmatter=post.metadata,
            links=links,
            updated_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            ingested_at=datetime.now(timezone.utc),
        )


def _extract_wikilinks(body: str) -> list[str]:
    return _WIKILINK_RE.findall(body)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/connectors/test_obsidian.py -v`
Expected: `2 passed`

If the `id` assertions fail because they don't match, recompute via
`python3 -c "import hashlib; print(hashlib.sha256(b'obsidian:note1.md').hexdigest())"`
and use the printed value — the relative path string must match exactly.

- [ ] **Step 7: Commit**

```bash
git add brain/connectors/obsidian.py tests/connectors/test_obsidian.py tests/conftest.py tests/fixtures/vault/note1.md tests/fixtures/vault/empty_frontmatter.md
git commit -m "feat: add Obsidian connector with frontmatter and link parsing"
```

---

## Task 8: Obsidian Connector — Merged Tag Extraction

**Files:**
- Modify: `brain/connectors/obsidian.py`
- Modify: `tests/connectors/test_obsidian.py`
- Create: `tests/fixtures/vault/code_fence_tag.md`

**Interfaces:**
- Consumes: `ObsidianConnector._parse_file` (Task 7).
- Produces: merged, deduplicated, sorted `tags` field combining frontmatter `tags:` and inline `#tag` occurrences, skipping any `#tag`-looking text inside fenced code blocks (``` ``` ``` or `~~~`).

- [ ] **Step 1: Create fixture vault file**

Create `tests/fixtures/vault/code_fence_tag.md`:

```
---
tags: [docs]
---
Some text with #real-tag outside a fence.

~~~
#fake-tag should not be extracted
~~~

More text with #another-real tag.
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/connectors/test_obsidian.py`:

```python
def test_iter_documents_merges_frontmatter_and_inline_tags(fixture_vault_path):
    docs = list(ObsidianConnector(fixture_vault_path).iter_documents())

    doc = _by_path(docs, "code_fence_tag.md")

    assert doc.tags == ["another-real", "docs", "real-tag"]


def test_iter_documents_merges_inline_tag_for_note_with_frontmatter_tags(fixture_vault_path):
    docs = list(ObsidianConnector(fixture_vault_path).iter_documents())

    doc = _by_path(docs, "note1.md")

    assert doc.tags == ["project", "work"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/connectors/test_obsidian.py -v`
Expected: `test_iter_documents_merges_frontmatter_and_inline_tags` FAILs — `doc.tags == ['docs']`, not `['another-real', 'docs', 'real-tag']`.

- [ ] **Step 4: Write minimal implementation**

In `brain/connectors/obsidian.py`, add the fence/tag regexes next to `_WIKILINK_RE`:

```python
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_INLINE_TAG_RE = re.compile(r"(?<!\S)#([A-Za-z0-9_/-]+)")
```

Replace the tag-computation line inside `_parse_file`:

```python
        tags = sorted(set(fm_tags))
```

with:

```python
        tags = sorted(set(fm_tags) | _extract_inline_tags(body))
```

Add the helper function alongside `_extract_wikilinks`:

```python
def _extract_inline_tags(body: str) -> set[str]:
    tags: set[str] = set()
    in_fence = False
    for line in body.split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        tags.update(_INLINE_TAG_RE.findall(line))
    return tags
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/connectors/test_obsidian.py -v`
Expected: `4 passed`

- [ ] **Step 6: Commit**

```bash
git add brain/connectors/obsidian.py tests/connectors/test_obsidian.py tests/fixtures/vault/code_fence_tag.md
git commit -m "feat: merge frontmatter and fence-aware inline tags in Obsidian connector"
```

---

## Task 9: Obsidian Connector — Per-File Error Isolation & Ignored Directories

**Files:**
- Modify: `brain/connectors/obsidian.py`
- Modify: `tests/connectors/test_obsidian.py`
- Create: `tests/fixtures/vault/malformed.md`
- Create: `tests/fixtures/vault/.obsidian/ignored.md`

**Interfaces:**
- Consumes: `ObsidianConnector.iter_documents` (Task 7).
- Produces: `iter_documents` now skips files under any `.obsidian/` directory and catches per-file parse exceptions (malformed YAML, bad encoding), logging `"skipped {path}: {error}"` and continuing rather than aborting the whole walk.

- [ ] **Step 1: Create fixture vault files**

Create `tests/fixtures/vault/malformed.md`:

```
---
title: [unclosed
---
Body text.
```

Create `tests/fixtures/vault/.obsidian/ignored.md`:

```
---
title: Should Be Ignored
---
This file lives inside the ignored .obsidian directory.
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/connectors/test_obsidian.py`:

```python
import logging


def test_iter_documents_skips_malformed_yaml_and_logs(fixture_vault_path, caplog):
    caplog.set_level(logging.INFO, logger="brain.connectors.obsidian")

    docs = list(ObsidianConnector(fixture_vault_path).iter_documents())

    assert all(d.path != "malformed.md" for d in docs)
    assert any("malformed.md" in record.message for record in caplog.records)


def test_iter_documents_ignores_dot_obsidian_directory(fixture_vault_path):
    docs = list(ObsidianConnector(fixture_vault_path).iter_documents())

    assert all(not d.path.startswith(".obsidian/") for d in docs)
    assert len(docs) == 3
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/connectors/test_obsidian.py -v`
Expected: FAIL — `test_iter_documents_skips_malformed_yaml_and_logs` raises the YAML parse error instead of skipping it; `test_iter_documents_ignores_dot_obsidian_directory` finds 4 docs (the ignored one is not filtered, and `malformed.md` errors before the count is reached).

- [ ] **Step 4: Write minimal implementation**

Add the logging import and ignore-dir constant near the top of `brain/connectors/obsidian.py`:

```python
import logging
```

```python
_IGNORE_DIRS = {".obsidian"}

logger = logging.getLogger(__name__)
```

Replace `iter_documents`:

```python
    def iter_documents(self) -> Iterator[Document]:
        for path in sorted(self.vault_path.rglob("*.md")):
            relative = path.relative_to(self.vault_path)
            if any(part in _IGNORE_DIRS for part in relative.parts):
                continue
            try:
                yield self._parse_file(path, relative)
            except Exception as e:
                logger.info("skipped %s: %s", relative, e)
                continue
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/connectors/test_obsidian.py -v`
Expected: `6 passed`

- [ ] **Step 6: Commit**

```bash
git add brain/connectors/obsidian.py tests/connectors/test_obsidian.py tests/fixtures/vault/malformed.md "tests/fixtures/vault/.obsidian/ignored.md"
git commit -m "feat: isolate per-file parse errors and skip .obsidian directory"
```

---

## Task 10: Core Ingest — `ingest_source`

**Files:**
- Create: `brain/core/__init__.py`
- Create: `brain/core/ingest.py`
- Test: `tests/core/test_ingest.py`

**Interfaces:**
- Consumes: `brain.models.Document` (Task 1), `brain.connectors.base.Connector` (Task 6), `brain.store.queries.upsert_document` / `delete_missing` (Tasks 3, 5).
- Produces: `IngestResult` dataclass (`upserted, skipped, deleted`) and `ingest_source(conn, source: str, connector: Connector) -> IngestResult`. Consumed by `cli/ingest.py` in Task 14.

- [ ] **Step 1: Create package marker**

Create `brain/core/__init__.py` with empty content.

- [ ] **Step 2: Write the failing tests**

Create `tests/core/test_ingest.py`:

```python
from datetime import datetime, timezone

from brain.core.ingest import ingest_source
from brain.models import Document
from brain.store import queries


def _doc(id, content="body", source="fake"):
    return Document(
        id=id,
        source=source,
        path=f"{id}.md",
        title=id,
        content=content,
        tags=[],
        frontmatter={},
        links=[],
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        ingested_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


class _FakeConnector:
    def __init__(self, docs):
        self._docs = docs

    def iter_documents(self):
        return iter(self._docs)


def test_ingest_source_upserts_all_documents(conn):
    connector = _FakeConnector([_doc("a"), _doc("b")])

    result = ingest_source(conn, "fake", connector)

    assert result.upserted == 2
    assert result.skipped == 0
    assert queries.get_by_id(conn, "a") is not None
    assert queries.get_by_id(conn, "b") is not None


def test_ingest_source_skips_document_that_fails_to_upsert(conn):
    connector = _FakeConnector([_doc("a"), _doc("b", content=None), _doc("c")])

    result = ingest_source(conn, "fake", connector)

    assert result.upserted == 2
    assert result.skipped == 1
    assert queries.get_by_id(conn, "a") is not None
    assert queries.get_by_id(conn, "b") is None
    assert queries.get_by_id(conn, "c") is not None


def test_ingest_source_deletes_rows_from_same_source_not_seen_this_run(conn):
    queries.upsert_document(conn, _doc("stale"))

    connector = _FakeConnector([_doc("a")])
    result = ingest_source(conn, "fake", connector)

    assert result.deleted == 1
    assert queries.get_by_id(conn, "stale") is None
    assert queries.get_by_id(conn, "a") is not None


def test_ingest_source_does_not_delete_rows_from_other_sources(conn):
    queries.upsert_document(conn, _doc("other-source-doc", source="other"))

    connector = _FakeConnector([_doc("a")])
    ingest_source(conn, "fake", connector)

    assert queries.get_by_id(conn, "other-source-doc") is not None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/core/test_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brain.core.ingest'`

- [ ] **Step 4: Write minimal implementation**

Create `brain/core/ingest.py`:

```python
import logging
import sqlite3
from dataclasses import dataclass

from brain.connectors.base import Connector
from brain.store import queries

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    upserted: int
    skipped: int
    deleted: int


def ingest_source(conn: sqlite3.Connection, source: str, connector: Connector) -> IngestResult:
    upserted = 0
    skipped = 0
    seen_ids: set[str] = set()
    for doc in connector.iter_documents():
        try:
            queries.upsert_document(conn, doc)
        except Exception as e:
            logger.info("skipped %s: %s", doc.path, e)
            skipped += 1
            continue
        seen_ids.add(doc.id)
        upserted += 1
    deleted = queries.delete_missing(conn, source, seen_ids)
    return IngestResult(upserted=upserted, skipped=skipped, deleted=deleted)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/core/test_ingest.py -v`
Expected: `4 passed`

- [ ] **Step 6: Commit**

```bash
git add brain/core/__init__.py brain/core/ingest.py tests/core/test_ingest.py
git commit -m "feat: add ingest_source with skip-and-continue and re-sync delete"
```

---

## Task 11: Core Search — `search_notes` & `get_note`

**Files:**
- Create: `brain/core/search.py`
- Test: `tests/core/test_search.py`

**Interfaces:**
- Consumes: `brain.store.queries.search` / `get_by_id` (Tasks 3-4).
- Produces: `BrainError(Exception)`, `search_notes(conn, query: str, source=None, tags=None, limit=10) -> list[SearchResult]`, `get_note(conn, id: str) -> Document`. Consumed by `mcp_server/tools.py` in Task 12.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_search.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/core/test_search.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brain.core.search'`

- [ ] **Step 3: Write minimal implementation**

Create `brain/core/search.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/core/test_search.py -v`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add brain/core/search.py tests/core/test_search.py
git commit -m "feat: add core search_notes and get_note with FTS5 escaping"
```

---

## Task 12: MCP Tool Handlers — `search_notes` & `get_note`

**Files:**
- Create: `brain/mcp_server/__init__.py`
- Create: `brain/mcp_server/tools.py`
- Test: `tests/mcp_server/test_tools.py`

**Interfaces:**
- Consumes: `brain.core.search.search_notes` / `get_note` / `BrainError` (Task 11).
- Produces: `ToolError(Exception)`, `ToolHandler` base class (`name`, `get_tool_description()`, `run_tool(args: dict)`), `SearchNotesToolHandler(conn)`, `GetNoteToolHandler(conn)`. Consumed by `mcp_server/server.py` in Task 13.

- [ ] **Step 1: Write the failing tests**

Create `tests/mcp_server/test_tools.py`:

```python
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
```

- [ ] **Step 2: Create package marker**

Create `brain/mcp_server/__init__.py` with empty content.

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/mcp_server/test_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brain.mcp_server.tools'`

- [ ] **Step 4: Write minimal implementation**

Create `brain/mcp_server/tools.py`:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/mcp_server/test_tools.py -v`
Expected: `6 passed`

- [ ] **Step 6: Commit**

```bash
git add brain/mcp_server/__init__.py brain/mcp_server/tools.py tests/mcp_server/test_tools.py
git commit -m "feat: add search_notes and get_note MCP tool handlers"
```

---

## Task 13: MCP Server Wiring

**Files:**
- Create: `brain/mcp_server/server.py`
- Test: `tests/mcp_server/test_server.py`

**Interfaces:**
- Consumes: `brain.mcp_server.tools.ToolHandler` / `SearchNotesToolHandler` / `GetNoteToolHandler` / `ToolError` (Task 12), `brain.store.db.get_connection` (Task 2).
- Produces: `build_app(conn) -> Server`, `resolve_db_path() -> Path`, `async run() -> None`, plus internal `_list_tools(handlers)` / `_call_tool(handlers, name, arguments)` coroutines. Consumed by `cli/serve.py` in Task 15.

- [ ] **Step 1: Write the failing tests**

Create `tests/mcp_server/test_server.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/mcp_server/test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brain.mcp_server.server'`

- [ ] **Step 3: Write minimal implementation**

Create `brain/mcp_server/server.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/mcp_server/test_server.py -v`
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add brain/mcp_server/server.py tests/mcp_server/test_server.py
git commit -m "feat: wire MCP server with tool dispatch and fail-fast DB check"
```

---

## Task 14: CLI — `brain-ingest`

**Files:**
- Create: `cli/__init__.py`
- Create: `cli/ingest.py`
- Test: `tests/test_cli_ingest.py`

**Interfaces:**
- Consumes: `brain.connectors.obsidian.ObsidianConnector` (Task 9), `brain.core.ingest.ingest_source` (Task 10), `brain.store.db.get_connection` (Task 2).
- Produces: `main() -> None` (the `brain-ingest` entry point declared in `pyproject.toml`'s `[project.scripts]`), exiting 1 on missing vault path, 0 with a summary line otherwise.

- [ ] **Step 1: Create package marker**

Create `cli/__init__.py` with empty content.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_cli_ingest.py`:

```python
import sqlite3

import pytest

from cli.ingest import main


def test_main_exits_1_when_vault_path_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        ["brain-ingest", "--vault", str(tmp_path / "nope"), "--db", str(tmp_path / "brain.db")],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    assert "Vault path does not exist" in capsys.readouterr().err


def test_main_ingests_fixture_vault_and_prints_summary(fixture_vault_path, tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "brain.db"
    monkeypatch.setattr(
        "sys.argv",
        ["brain-ingest", "--vault", str(fixture_vault_path), "--db", str(db_path)],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "upserted: 3, skipped: 0, deleted: 0" in out

    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    assert count == 3
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cli.ingest'`

- [ ] **Step 4: Write minimal implementation**

Create `cli/ingest.py`:

```python
import argparse
import os
import sys
from pathlib import Path

from brain.connectors.obsidian import ObsidianConnector
from brain.core.ingest import ingest_source
from brain.store.db import get_connection

DEFAULT_DB_PATH = Path.home() / ".brain" / "brain.db"


def main() -> None:
    parser = argparse.ArgumentParser(prog="brain-ingest")
    parser.add_argument("--vault", default=os.environ.get("BRAIN_VAULT_PATH"))
    parser.add_argument("--db", default=str(os.environ.get("BRAIN_DB_PATH", DEFAULT_DB_PATH)))
    args = parser.parse_args()

    if not args.vault:
        print("Vault path required: pass --vault or set BRAIN_VAULT_PATH", file=sys.stderr)
        raise SystemExit(1)

    vault_path = Path(args.vault)
    if not vault_path.exists():
        print(f"Vault path does not exist: {vault_path}", file=sys.stderr)
        raise SystemExit(1)

    conn = get_connection(Path(args.db))
    connector = ObsidianConnector(vault_path)
    result = ingest_source(conn, "obsidian", connector)
    print(f"upserted: {result.upserted}, skipped: {result.skipped}, deleted: {result.deleted}")
    raise SystemExit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_ingest.py -v`
Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add cli/__init__.py cli/ingest.py tests/test_cli_ingest.py
git commit -m "feat: add brain-ingest CLI entry point"
```

---

## Task 15: CLI — `brain-serve` & End-to-End Stdio Test

**Files:**
- Create: `cli/serve.py`
- Test: `tests/test_stdio.py`

**Interfaces:**
- Consumes: `brain.mcp_server.server.run` (Task 13), `brain.connectors.obsidian.ObsidianConnector` (Task 9), `brain.core.ingest.ingest_source` (Task 10), `brain.store.db.get_connection` (Task 2).
- Produces: `main() -> None` (the `brain-serve` entry point declared in `pyproject.toml`'s `[project.scripts]`), runnable as `python -m cli.serve`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_stdio.py`:

```python
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from brain.connectors.obsidian import ObsidianConnector
from brain.core.ingest import ingest_source
from brain.store.db import get_connection


def _make_fixture_db(tmp_path, fixture_vault_path):
    db_path = tmp_path / "brain.db"
    conn = get_connection(db_path)
    ingest_source(conn, "obsidian", ObsidianConnector(fixture_vault_path))
    conn.close()
    return db_path


async def test_search_notes_and_get_note_over_stdio(tmp_path, fixture_vault_path):
    db_path = _make_fixture_db(tmp_path, fixture_vault_path)
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "cli.serve"],
        env={**os.environ, "BRAIN_DB_PATH": str(db_path)},
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            search_result = await session.call_tool("search_notes", {"query": "fence"})
            hits = json.loads(search_result.content[0].text)
            assert len(hits) == 1
            note_id = hits[0]["id"]

            get_result = await session.call_tool("get_note", {"id": note_id})
            doc = json.loads(get_result.content[0].text)
            assert doc["id"] == note_id
            assert doc["path"] == "code_fence_tag.md"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stdio.py -v`
Expected: FAIL — the subprocess command `python -m cli.serve` errors immediately because `cli/serve.py` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Create `cli/serve.py`:

```python
import asyncio

from brain.mcp_server.server import run


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_stdio.py -v`
Expected: `1 passed`

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest -v`
Expected: all tests across every prior task pass (around 45 total).

- [ ] **Step 6: Commit**

```bash
git add cli/serve.py tests/test_stdio.py
git commit -m "feat: add brain-serve CLI entry point and end-to-end stdio test"
```

---

## Self-Review

**Spec coverage:**
- Architecture (thin MCP adapter / Core / Store / Connector layering): Tasks 1-13.
- `Document` model: Task 1.
- SQLite + FTS5 schema, external-content table with sync triggers: Task 2.
- `store/queries.py` full surface (`upsert_document`, `search`, `get_by_id`, `delete_missing`, `list_recent`): Tasks 3-5.
- Obsidian connector (filesystem read, frontmatter, merged tags, fence-aware, wikilinks, id hashing, per-file error isolation, `.obsidian` skip): Tasks 7-9.
- Ingestion data flow (idempotent schema creation, generator-based walk, upsert, full re-sync delete, summary print): Tasks 2, 7, 10, 14.
- Query data flow (validate, escape, search, snippet, tool-level id passthrough): Tasks 4, 11, 12.
- MCP tool surface (`search_notes`, `get_note`): Task 12.
- Error handling (per-file skip, vault-missing fail-fast, DB-missing fail-fast, empty-query rejection, unknown-id `ToolError`): Tasks 9, 11, 12, 13, 14.
- Testing strategy (fixture vault, in-memory store tests, fake-connector core tests, direct tool-handler tests, end-to-end stdio test, no SQLite mocking): Tasks 1-15.
- Out-of-scope items (semantic search, write actions, additional sources, chunking, file watching, Local REST API) are not implemented anywhere in this plan, matching the spec.

**Placeholder scan:** no `TBD`/`TODO` markers; every step has runnable code or an exact shell command with an expected result.

**Type consistency:** `Document` fields (Task 1) are used identically in every later task. `SearchResult` (Task 4) fields match what `tools.py` (Task 12) reads. `Connector.iter_documents` (Task 6) matches `ObsidianConnector.iter_documents` (Task 7) and the `_FakeConnector` used in Task 10. `ToolHandler.run_tool` / `get_tool_description` (Task 12) match how `build_app` (Task 13) calls them. `ingest_source(conn, source, connector)` signature (Task 10) matches its call sites in Tasks 14-15.

---

Plan complete and saved to `docs/superpowers/plans/2026-06-18-second-brain-mvp.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
