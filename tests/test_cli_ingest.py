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
