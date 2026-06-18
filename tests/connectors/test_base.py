from brain.connectors.base import Connector


class _FakeConnector:
    def iter_documents(self):
        return iter([])


def test_fake_connector_satisfies_protocol():
    assert isinstance(_FakeConnector(), Connector)


def test_object_without_method_does_not_satisfy_protocol():
    assert not isinstance(object(), Connector)
