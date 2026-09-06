from system_intelligence.discovery.frontmatter import parse_frontmatter


def test_parse_frontmatter_extracts_fields() -> None:
    text = "---\nname: x\ndescription: y\n---\nBody.\n"
    assert parse_frontmatter(text) == {"name": "x", "description": "y"}


def test_parse_frontmatter_returns_none_without_a_block() -> None:
    assert parse_frontmatter("Just plain text.\n") is None


def test_parse_frontmatter_strips_quotes() -> None:
    text = "---\nname: \"quoted\"\ndescription: 'single'\n---\n"
    assert parse_frontmatter(text) == {"name": "quoted", "description": "single"}


def test_parse_frontmatter_ignores_lines_without_a_colon() -> None:
    text = "---\nname: x\nnot a field\ndescription: y\n---\n"
    assert parse_frontmatter(text) == {"name": "x", "description": "y"}


def test_parse_frontmatter_blank_block_returns_empty_dict() -> None:
    text = "---\n\n---\nBody.\n"
    assert parse_frontmatter(text) == {}
