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
