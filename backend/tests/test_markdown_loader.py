from __future__ import annotations

from app.ingestion.loaders.markdown_loader import MarkdownLoader
from app.ingestion.loaders.registry import SUPPORTED_EXTENSIONS, get_loader

DOCUMENT = """# Guide

Intro paragraph.

## Setup

Install the thing.

### Prerequisites

Python 3.12.

## Usage

Run the thing.
"""


def write(tmp_path, name: str, body: str):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_heading_hierarchy_becomes_the_section_path(tmp_path):
    sections = MarkdownLoader().load(write(tmp_path, "guide.md", DOCUMENT))

    assert [section.heading_path for section in sections] == [
        ["Guide"],
        ["Guide", "Setup"],
        ["Guide", "Setup", "Prerequisites"],
        ["Guide", "Usage"],
    ]


def test_sibling_heading_pops_the_deeper_level(tmp_path):
    sections = MarkdownLoader().load(write(tmp_path, "guide.md", DOCUMENT))
    usage = sections[-1]

    assert usage.heading_path == ["Guide", "Usage"]
    assert usage.text.strip() == "Run the thing."


def test_hashes_inside_fenced_code_are_not_headings(tmp_path):
    body = "# Title\n\n```python\n# not a heading\n```\n"

    sections = MarkdownLoader().load(write(tmp_path, "code.md", body))

    assert len(sections) == 1
    assert "# not a heading" in sections[0].text


def test_registry_resolves_markdown_and_reports_supported_extensions(tmp_path):
    loader = get_loader("notes.md")

    assert isinstance(loader, MarkdownLoader)
    assert ".pdf" in SUPPORTED_EXTENSIONS
    assert loader.load(write(tmp_path, "notes.md", DOCUMENT))
