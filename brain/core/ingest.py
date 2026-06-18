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
