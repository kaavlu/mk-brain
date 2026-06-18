from pathlib import Path

import pytest

from brain.store.db import get_connection


@pytest.fixture
def conn():
    connection = get_connection(":memory:")
    yield connection
    connection.close()


FIXTURE_VAULT = Path(__file__).parent / "fixtures" / "vault"


@pytest.fixture
def fixture_vault_path() -> Path:
    return FIXTURE_VAULT
