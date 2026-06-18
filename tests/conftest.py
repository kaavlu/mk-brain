import pytest

from brain.store.db import get_connection


@pytest.fixture
def conn():
    connection = get_connection(":memory:")
    yield connection
    connection.close()
