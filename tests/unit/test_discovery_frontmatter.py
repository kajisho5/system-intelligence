from system_intelligence.discovery.frontmatter import (
    parse_frontmatter,
    split_glob_list,
    split_tool_list,
)


def test_parse_frontmatter_extracts_fields() -> None:
    text = "---\nname: x\ndescription: y\n---\nBody.\n"
    assert parse_frontmatter(text) == {"name": "x", "description": "y"}


def test_parse_frontmatter_returns_none_without_a_block() -> None:
    assert parse_frontmatter("Just plain text.\n") is None


def test_parse_frontmatter_strips_quotes() -> None:
    text = "---\nname: \"quoted\"\ndescription: 'single'\n---\n"
    assert parse_frontmatter(text) == {"name": "quoted", "description": "single"}


def test_parse_frontmatter_quoted_value_containing_the_other_quote_character_at_the_boundary() -> (
    None
):
    """`str.strip('"\\'')` (the previous implementation) strips *any run*
    of either quote character from either end, not a matched delimiter
    pair -- so a single-quoted value whose own content ends with a
    double-quoted term right at the boundary (a realistic Skill
    description, e.g. mentioning a file extension in quotes) got eaten
    past its real closing delimiter, silently truncating real content."""
    text = "---\nname: x\ndescription: 'Use this for \".json\"'\n---\n"
    assert parse_frontmatter(text) == {"name": "x", "description": 'Use this for ".json"'}


def test_parse_frontmatter_quoted_value_starting_with_the_other_quote_character() -> None:
    text = "---\nname: x\ndescription: \"'quoted' term leading\"\n---\n"
    assert parse_frontmatter(text) == {"name": "x", "description": "'quoted' term leading"}


def test_parse_frontmatter_mismatched_quotes_left_unstripped() -> None:
    """A value whose first and last characters are quote characters but
    not the *same* one is not a validly-quoted scalar -- left as-is
    rather than guessing which end is the real delimiter."""
    text = "---\nname: x\ndescription: 'mismatched\"\n---\n"
    assert parse_frontmatter(text) == {"name": "x", "description": "'mismatched\""}


def test_parse_frontmatter_ignores_lines_without_a_colon() -> None:
    text = "---\nname: x\nnot a field\ndescription: y\n---\n"
    assert parse_frontmatter(text) == {"name": "x", "description": "y"}


def test_parse_frontmatter_blank_block_returns_empty_dict() -> None:
    text = "---\n\n---\nBody.\n"
    assert parse_frontmatter(text) == {}


def test_split_tool_list_splits_on_commas() -> None:
    assert split_tool_list("Read, Grep, Glob") == ["Read", "Grep", "Glob"]


def test_split_tool_list_splits_on_whitespace() -> None:
    assert split_tool_list("Read Grep") == ["Read", "Grep"]


def test_split_tool_list_trims_whitespace() -> None:
    assert split_tool_list("  Read ,  Write  ") == ["Read", "Write"]


def test_split_tool_list_keeps_a_comma_inside_parentheses_as_one_token() -> None:
    """`Agent(worker, researcher)` (code.claude.com/docs/en/sub-agents,
    "restrict which subagent types it can spawn") is one specifier whose
    parenthesized argument list itself contains a comma -- a naive
    `str.split(",")` would incorrectly break it into two tokens."""
    assert split_tool_list("Agent(worker, researcher), Read, Bash") == [
        "Agent(worker, researcher)",
        "Read",
        "Bash",
    ]


def test_split_tool_list_keeps_a_space_inside_parentheses_as_one_token() -> None:
    """`Bash(git add *)` (code.claude.com/docs/en/skills's `allowed-tools`
    examples) has a space inside its parenthesized argument."""
    assert split_tool_list("Bash(git add *) Bash(git commit *)") == [
        "Bash(git add *)",
        "Bash(git commit *)",
    ]


def test_split_tool_list_empty_string_returns_empty_list() -> None:
    assert split_tool_list("") == []


def test_split_glob_list_splits_on_commas() -> None:
    assert split_glob_list("src/**/*.ts, docs/**/*.md") == ["src/**/*.ts", "docs/**/*.md"]


def test_split_glob_list_trims_whitespace() -> None:
    assert split_glob_list("  src/*.py  ,  docs/*.md  ") == ["src/*.py", "docs/*.md"]


def test_split_glob_list_keeps_a_comma_inside_braces_as_one_pattern() -> None:
    """`src/**/*.{ts,tsx}` (bash/zsh/glob-library brace expansion) is one
    pattern whose brace-expansion group itself contains a comma -- a
    naive `str.split(",")` would incorrectly break it into two patterns."""
    assert split_glob_list("src/**/*.{ts,tsx}, docs/**/*.md") == [
        "src/**/*.{ts,tsx}",
        "docs/**/*.md",
    ]


def test_split_glob_list_never_splits_on_bare_whitespace() -> None:
    """Unlike `split_tool_list`, only a comma separates patterns -- the
    `paths` field is documented as comma-separated, not space-separated,
    and a glob pattern could itself legitimately contain a space."""
    assert split_glob_list("src/my dir/*.py") == ["src/my dir/*.py"]


def test_split_glob_list_empty_string_returns_empty_list() -> None:
    assert split_glob_list("") == []
