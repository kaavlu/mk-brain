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
