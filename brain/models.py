from dataclasses import dataclass
from datetime import datetime


@dataclass
class Document:
    id: str
    source: str
    path: str
    title: str
    content: str
    tags: list[str]
    frontmatter: dict
    links: list[str]
    updated_at: datetime
    ingested_at: datetime
