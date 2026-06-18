from datetime import datetime, timezone

from brain.connectors.obsidian import ObsidianConnector


def _by_path(docs, path):
    return next(d for d in docs if d.path == path)


def test_iter_documents_parses_frontmatter_title_links_and_id(fixture_vault_path):
    docs = list(ObsidianConnector(fixture_vault_path).iter_documents())

    doc = _by_path(docs, "note1.md")
    stat = (fixture_vault_path / "note1.md").stat()

    assert doc.id == "d34256f07c2bc72744fe80796e32eeb8ab7229140eb86d0e37ccbd98a0aa149d"
    assert doc.source == "obsidian"
    assert doc.title == "Note One"
    assert doc.content.strip() == (
        "This is the body with an inline #work tag and a link to [[Note Two]]."
    )
    assert doc.frontmatter == {"title": "Note One", "tags": ["project"]}
    assert doc.links == ["Note Two"]
    assert doc.updated_at == datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    assert (datetime.now(timezone.utc) - doc.ingested_at).total_seconds() < 5


def test_iter_documents_falls_back_to_filename_stem_for_title(fixture_vault_path):
    docs = list(ObsidianConnector(fixture_vault_path).iter_documents())

    doc = _by_path(docs, "empty_frontmatter.md")

    assert doc.id == "e3bde0a353cbf05f1130f98114fd3251801b328f92210143827c3348edb7e1ac"
    assert doc.title == "empty_frontmatter"
    assert doc.content.strip() == (
        "No frontmatter here, just a plain note with an inline #note tag."
    )
    assert doc.frontmatter == {}
    assert doc.links == []
