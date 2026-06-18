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
