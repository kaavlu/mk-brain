# Second Brain MCP — MVP Design

## Goal

A local-first personal "Second Brain" that exposes persistent context (starting
with an Obsidian vault) to Claude Code through a single MCP server, so coding
sessions can pull up prior project decisions, notes, and implementation logs
without Claude Code connecting to many individual source-specific MCP servers.

MVP scope: read-only question-answering over the vault via keyword/full-text
search. No semantic search/embeddings/ranking, no write actions — both are
explicitly deferred.

## Principles (from project requirements)

- The MCP server is a thin protocol adapter, not the application.
- Brain Core owns product/application logic (query building, result assembly).
- Connectors normalize external sources into one internal document model.
- Ingestion happens outside the MCP request path.
- Write actions come later and will require explicit confirmation.

## Architecture

```
Claude Code (MCP client)
        │  stdio (MCP protocol)
        ▼
┌───────────────────────┐
│   Brain MCP Server     │  thin adapter: translates MCP tool calls
│   (brain/mcp_server)   │  ↔ Core function calls. No business logic.
└───────────┬───────────┘
            │  in-process call
            ▼
┌───────────────────────┐
│      Brain Core         │  owns query logic: builds FTS queries,
│      (brain/core)       │  assembles results, applies filters.
└───────────┬───────────┘
            │  reads
            ▼
┌───────────────────────┐
│   Local Brain Store     │  SQLite + FTS5, single .db file on disk.
│   (brain/store)         │  Documents table + FTS index.
└───────────▲───────────┘
            │  writes (separate process, CLI-triggered)
┌───────────┴───────────┐
│  Ingestion Pipeline      │  `brain-ingest` CLI entry point.
│  (brain/connectors +     │  Connector(s) → normalize → write to Store.
│   brain/core ingest fns) │
└───────────▲───────────┘
            │  reads
┌───────────┴───────────┐
│     Obsidian Vault       │  source of truth, read directly from disk.
└───────────────────────┘
```

Two entry points, one shared codebase, one SQLite file:

- **`brain-serve`** — long-lived stdio MCP server, started by Claude Code per
  its MCP client config. Only ever *reads* from the Store.
- **`brain-ingest`** — short-lived CLI command, run manually whenever you want
  the Store refreshed. Only ever *writes* to the Store. Never runs inside an
  MCP request, so ingestion latency/failures can't block a query.

Both entry points import the same `brain` package, so the document model and
store schema are defined exactly once.

## Project Structure

```
brain/
  __init__.py
  models.py             # Document dataclass, shared types
  store/
    __init__.py
    db.py                # connection mgmt, schema creation/migration
    schema.sql            # CREATE TABLE statements
    queries.py             # insert_document(), search(), get_by_id(), list_recent()
  core/
    __init__.py
    ingest.py              # ingest_source(connector) -> writes via store.queries
    search.py               # search_notes(query, filters) -> assembles results from store
  connectors/
    __init__.py
    base.py                  # Connector protocol: yields raw items
    obsidian.py                # ObsidianConnector: walks vault, parses .md -> Document
  mcp_server/
    __init__.py
    server.py                  # MCP server setup, tool registration
    tools.py                     # search_notes / get_note tool handlers -> call core.search
cli/
  ingest.py                      # entry point: brain-ingest
  serve.py                        # entry point: brain-serve
pyproject.toml
```

Single Python package, layered internally — chosen over splitting
ingest/serve into separate projects (would duplicate the document model and
schema) or flat scripts (would erode the Core/adapter/connector boundaries as
soon as a second source is added).

## Internal Document Model

```python
@dataclass
class Document:
    id: str            # stable hash of (source, path) — same note re-ingested = same id
    source: str         # "obsidian" (later: "gdocs", "gmail", "github", ...)
    path: str            # vault-relative file path
    title: str
    content: str          # raw markdown body (frontmatter stripped)
    tags: list[str]        # frontmatter `tags:` + inline `#tag` occurrences, merged & deduped
    frontmatter: dict     # raw YAML frontmatter, JSON-serialized in storage
    links: list[str]       # outgoing [[wikilinks]], unresolved
    updated_at: datetime    # file mtime
    ingested_at: datetime
```

Every connector's only job is to produce a list of `Document` objects.
Nothing downstream knows what "Obsidian" is.

## Local Brain Store

SQLite with FTS5, single `.db` file under `~/.brain/brain.db`.

```sql
CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    path TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT,            -- JSON array
    frontmatter TEXT,        -- JSON object
    links TEXT,             -- JSON array
    updated_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE documents_fts USING fts5(
    title, content, tags,
    content='documents', content_rowid='rowid'
);
-- triggers keep documents_fts in sync on insert/update/delete
```

`documents_fts` is an *external content* FTS5 table: `documents` stays the
readable source of truth, the FTS index is purely a search index kept in sync
by triggers — no dual-write logic in application code.

`store/queries.py` surface:
- `upsert_document(conn, doc)` — insert or replace by `id`
- `search(conn, query, source=None, tags=None, limit=10)` — `MATCH` against
  `documents_fts`, joins back to `documents`, returns ranked snippets via
  FTS5 `snippet()`
- `get_by_id(conn, id)`
- `delete_missing(conn, source, keep_ids)` — removes rows from a source not
  present in the latest ingestion run
- `list_recent(conn, limit)` — not wired to an MCP tool yet, but cheap to have

## Connector: Obsidian (direct filesystem read)

Reads the vault directly from disk rather than going through the Obsidian
Local REST API plugin. Decision and trade-offs:

- **Chosen: direct filesystem read.** No dependency on the Obsidian app being
  open, no plugin install, no API key/host/port/cert config — `brain-ingest`
  can run any time, including headless. Failure mode is just file I/O, a much
  smaller surface than HTTP (auth, self-signed certs, connection refused).
- **Rejected for now: Local REST API plugin** (the approach used by the
  `mcp-obsidian` reference project). Its real advantage — frontmatter/tag
  parsing identical to what Obsidian itself computes, and live writes that
  show up correctly in Obsidian's running UI/sync — only pays for itself once
  write actions exist. Paying the operational cost (Obsidian must be running,
  plugin enabled, API key configured) for a read-only MVP that doesn't use
  the live-write capability doesn't fit the local-first/simple goal. Revisit
  this specifically for writes when that phase starts; reads can stay
  filesystem-based even if writes later go through the REST API.

Behavior, with two ideas borrowed from inspecting `mcp-obsidian`'s
implementation even though the access mechanism differs:

- Walks the vault directory (skipping `.obsidian/` and other configured
  ignore patterns), yields one `Document` per `.md` file.
- Parses YAML frontmatter (`python-frontmatter`), extracts inline `#tags` via
  a fence-aware regex (skips fenced code blocks), extracts `[[wikilinks]]`
  via regex, computes `id = sha256(f"obsidian:{relative_path}")`.
- **Merged tag set** (borrowed idea): a note's tags are frontmatter `tags:`
  plus inline `#tag` occurrences in the body, deduplicated into one set —
  matches how `mcp-obsidian` exposes tags, just computed locally instead of
  via the plugin's API.
- **Per-file error isolation** (borrowed idea, from `mcp-obsidian`'s
  `get_batch_file_contents` pattern of catching errors per-file and
  continuing): if a file has malformed YAML or bad encoding, log
  `"skipped {path}: {error}"` and continue — one bad note never aborts the
  whole ingestion run.
- No chunking in MVP — a whole note is one row / one FTS document. Chunking
  is a retrieval-quality concern explicitly deferred.

## Data Flow

**Ingestion** (`brain-ingest`, run manually):

1. CLI opens a connection to `~/.brain/brain.db`, creating the schema if
   missing (`CREATE TABLE IF NOT EXISTS`, idempotent).
2. `ObsidianConnector.iter_documents()` walks the vault as a generator (not a
   full in-memory list, keeps memory flat regardless of vault size), parsing
   each file as described above and skipping ones that fail to parse.
3. `core.ingest.ingest_source` upserts each successfully-parsed `Document`;
   SQLite triggers mirror the change into `documents_fts`.
4. After the full walk, rows with `source='obsidian'` not present in this
   run's `seen_ids` are deleted — full re-sync semantics, handles
   renamed/deleted notes. No incremental diffing in MVP; fine at personal
   vault scale.
5. CLI prints a summary (`upserted: 142, skipped: 1, deleted: 3`) and exits 0.
   Skips are visible in output but not treated as fatal.

**Query** (Claude Code asks a question mid-session):

1. Claude Code sends an MCP `tools/call` for `search_notes` with
   `{query, source?, tags?, limit?}` over stdio.
2. `mcp_server/tools.py` handler calls `core.search.search_notes(conn, ...)`.
3. `core.search` validates the query (rejects empty/whitespace), builds the
   FTS5 `MATCH` query (escaping special FTS5 syntax characters), optionally
   filters by `source`/`tags`, delegates to `store.queries.search`.
4. `store.queries.search` runs the SQL, returns ranked rows with
   `snippet()`-generated excerpts, mapped to `SearchResult` objects
   (`{id, source, path, title, snippet, score}`).
5. Tool handler serializes results to MCP content blocks, including each
   result's `id` so Claude Code can follow up with `get_note(id)` for full
   content of the most relevant hit(s).

The connection used by `brain-serve` is opened once at startup and reused
across calls. `brain-ingest` and `brain-serve` can safely run concurrently —
SQLite's default journal mode handles one writer + readers without extra
locking code.

## MCP Tool Surface (MVP)

- `search_notes(query, source?, tags?, limit=10)` → ranked snippets/matches
- `get_note(id)` → full content of a specific document

`list_recent` and richer filtering are easy additions later given
`store.queries.list_recent` already exists, but aren't wired to a tool yet —
no current use case for them in the MVP.

## Error Handling

**Ingestion:**
- Per-file parse errors: caught and skipped, never abort the run.
- Vault path missing/inaccessible: fail fast before touching the DB
  (`Vault path does not exist: {path}`), exit code 1.
- DB file locked/corrupt: surfaced as-is from SQLite, no custom recovery —
  this is a personal local tool; re-running ingestion against a fresh file
  is an acceptable recovery path.

**Serving:**
- `get_note` with unknown `id`: raises an MCP `ToolError` with a clear
  message (`No document with id {id}`), not a stack trace — mirrors the
  explicit-error-with-message style used throughout `mcp-obsidian`'s tool
  handlers.
- `search_notes` with empty/whitespace query: rejected at the `core.search`
  layer with a `ToolError` before reaching SQLite (an empty FTS5 `MATCH` is a
  SQL error, not a meaningful "no results").
- DB file missing at server startup: fail fast with
  `Brain store not found at {path}. Run 'brain-ingest' first.` rather than
  starting and silently returning empty results for every query.
- No retries, circuit breakers, or timeouts beyond SQLite's defaults — there
  is no network call in the read path.

## Testing

- **Connector tests**: fixture vault under `tests/fixtures/vault/` with
  varied frontmatter/tags/links/edge cases (empty frontmatter, inline tag
  inside a code fence that must NOT be extracted, malformed YAML that must be
  skipped). Assert exact `Document` objects produced.
- **Store tests**: in-memory SQLite (`:memory:`) for `upsert_document`,
  `search`, `get_by_id`, `delete_missing` — fast, run on every change.
- **Core tests**: `ingest_source` with a fake connector (one `Document`
  designed to raise) to verify skip-and-continue and re-sync delete logic;
  `search_notes` for query validation and filter application.
- **MCP tool tests**: call tool handlers directly with constructed args dicts,
  assert on returned content; plus an end-to-end stdio test that spins up the
  real MCP server subprocess against a fixture DB and exercises `tools/call`
  over stdio — mirroring the `tests/test_tools.py` / `tests/test_stdio.py`
  pattern found in the `mcp-obsidian` reference repo.
- No mocking of SQLite — tests hit a real (in-memory or temp-file) DB
  throughout.

## Out of Scope (MVP)

- Semantic search / embeddings / ranking beyond FTS5's built-in ranking.
- Write actions (append/patch/delete notes) — later phase, will require
  explicit confirmation when built.
- Additional sources (Google Docs, Gmail, Calendar, GitHub, ChatGPT/Claude
  conversation history) — the connector/document-model boundary is designed
  to make these additive later, but none are built in this MVP.
- Chunking of long notes for retrieval quality.
- Incremental/watched ingestion (file watcher, on-save triggers) — ingestion
  is a manual, full-resync CLI command only.
- Obsidian Local REST API integration — revisit specifically when write
  actions are designed.
