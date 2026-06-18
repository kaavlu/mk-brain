from typing import Iterator, Protocol, runtime_checkable

from brain.models import Document


@runtime_checkable
class Connector(Protocol):
    def iter_documents(self) -> Iterator[Document]:
        ...
