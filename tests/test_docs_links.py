"""Relative links in the README and docs resolve, including heading anchors."""

import re
from pathlib import Path

import pytest

FILES = [Path("README.md"), *sorted(Path("docs").glob("*.md"))]
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def _slug(heading: str) -> str:
    """GitHub's anchor for a heading: lowercase, punctuation dropped, spaces to hyphens."""
    text = re.sub(r"[`*_]", "", heading.strip().lower())
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s", "-", text)


def _anchors(path: Path) -> set[str]:
    return {_slug(line.lstrip("#")) for line in path.read_text().splitlines() if line.startswith("#")}


def _links(path: Path):
    text = re.sub(r"```.*?```", "", path.read_text(), flags=re.DOTALL)  # ignore code blocks
    for target in LINK.findall(text):
        if not target.startswith(("http://", "https://", "mailto:")):
            yield target


@pytest.mark.parametrize("path", FILES, ids=str)
def test_relative_links_resolve(path):
    for target in _links(path):
        file_part, _, anchor = target.partition("#")
        dest = path if not file_part else (path.parent / file_part).resolve()
        assert dest.exists(), f"{path}: {target} points to a missing file"
        if anchor and dest.suffix == ".md":
            assert anchor in _anchors(dest), f"{path}: {target} points to a missing heading"
