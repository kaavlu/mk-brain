import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import frontmatter

from brain.models import Document

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")


class ObsidianConnector:
    def __init__(self, vault_path: Path):
        self.vault_path = Path(vault_path)

    def iter_documents(self) -> Iterator[Document]:
        for path in sorted(self.vault_path.rglob("*.md")):
            relative = path.relative_to(self.vault_path)
            yield self._parse_file(path, relative)

    def _parse_file(self, path: Path, relative: Path) -> Document:
        raw = path.read_text(encoding="utf-8")
        post = frontmatter.loads(raw)
        body = post.content
        fm_tags = post.metadata.get("tags") or []
        if isinstance(fm_tags, str):
            fm_tags = [fm_tags]
        tags = sorted(set(fm_tags))
        links = _extract_wikilinks(body)
        title = post.metadata.get("title") or path.stem
        stat = path.stat()
        doc_id = hashlib.sha256(
            f"obsidian:{relative.as_posix()}".encode()
        ).hexdigest()
        return Document(
            id=doc_id,
            source="obsidian",
            path=relative.as_posix(),
            title=title,
            content=body,
            tags=tags,
            frontmatter=post.metadata,
            links=links,
            updated_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            ingested_at=datetime.now(timezone.utc),
        )


def _extract_wikilinks(body: str) -> list[str]:
    return _WIKILINK_RE.findall(body)
