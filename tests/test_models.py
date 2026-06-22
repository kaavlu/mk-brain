from datetime import datetime, timezone

from brain.models import Document


def test_document_holds_all_fields():
    doc = Document(
        id="abc123",
        source="obsidian",
        path="notes/a.md",
        title="A",
        content="body",
        tags=["x"],
        frontmatter={"title": "A"},
        links=["B"],
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        ingested_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
    )

    assert doc.id == "abc123"
    assert doc.source == "obsidian"
    assert doc.path == "notes/a.md"
    assert doc.title == "A"
    assert doc.content == "body"
    assert doc.tags == ["x"]
    assert doc.frontmatter == {"title": "A"}
    assert doc.links == ["B"]
    assert doc.updated_at == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert doc.ingested_at == datetime(2024, 1, 2, tzinfo=timezone.utc)
