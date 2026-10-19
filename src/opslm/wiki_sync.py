"""Mirror selected repository docs into the project wiki, which is a separate git repository.

The repo's ``docs/`` are the source of truth (they are reviewed in pull requests and versioned with
the code); the wiki is the easier place to read them. Wikis cannot take pull requests, so the
mirror is written by this tool:

    python -m opslm.wiki_sync            # show what would change
    python -m opslm.wiki_sync --push     # commit and push the changes to the wiki

Relative links in the docs are rewritten so they work on the wiki: links between mirrored pages
become wiki links, and links to anything else point at the file on GitHub.
"""

from __future__ import annotations

import argparse
import posixpath
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

REPO_URL = "https://github.com/iamdirk-gc/opslm"
WIKI_GIT_URL = f"{REPO_URL}.wiki.git"

# repository file -> wiki page name (the page title is the name with hyphens as spaces)
PAGES: dict[str, str] = {
    "docs/status.md": "Status",
    "docs/decisions.md": "Decisions-for-the-Project-Owner",
}
# one line per page on the wiki Home, in the order they should appear
HOME_ENTRIES: dict[str, str] = {
    "Status": "[[Status]]: where the project stands against the board and the November 9 release",
    "Decisions-for-the-Project-Owner": "[[Decisions for the Project Owner]]: the open questions that need the owner's call",
}

_LINK = re.compile(r"(\[[^\]]*\]\()([^)\s]+)(\))")
_FENCE = re.compile(r"(```.*?```)", re.DOTALL)


def _rewrite_target(target: str, source: str, pages: dict[str, str]) -> str:
    if target.startswith(("http://", "https://", "mailto:", "#")):
        return target
    file_part, _, anchor = target.partition("#")
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), file_part))
    suffix = f"#{anchor}" if anchor else ""
    if resolved in pages:
        return pages[resolved] + suffix
    kind = "tree" if target.rstrip("#").endswith("/") else "blob"
    return f"{REPO_URL}/{kind}/main/{resolved}{suffix}"


def rewrite_links(text: str, source: str, pages: dict[str, str] | None = None) -> str:
    """Make a doc's relative links work from the wiki. Code blocks are left alone."""
    pages = PAGES if pages is None else pages
    parts = _FENCE.split(text)
    for i in range(0, len(parts), 2):  # odd parts are fenced code
        parts[i] = _LINK.sub(
            lambda m: f"{m.group(1)}{_rewrite_target(m.group(2), source, pages)}{m.group(3)}", parts[i])
    return "".join(parts)


def _same_title(heading: str, page: str) -> bool:
    norm = lambda s: re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
    return norm(heading) == norm(page.replace("-", " "))


def to_wiki_page(source: str, text: str, page: str, today: date) -> str:
    """The wiki text for a repository doc: its own title dropped when the wiki already shows the
    same one, links rewritten, and a footer saying where it comes from."""
    lines = text.rstrip("\n").split("\n")
    if lines and lines[0].startswith("# ") and _same_title(lines[0][2:], page):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    body = rewrite_links("\n".join(lines), source)
    footer = (f"_Mirrored from [`{source}`]({REPO_URL}/blob/main/{source}) on {today.isoformat()}. "
              "Edit that file and run `python -m opslm.wiki_sync`, not this page._")
    return f"{body}\n\n---\n\n{footer}\n"


def update_home(home: str) -> str:
    """Add the mirrored pages to the wiki Home page's list, once each."""
    out = home.rstrip("\n")
    for page, line in HOME_ENTRIES.items():
        if f"[[{page.replace('-', ' ')}]]" not in out and f"|{page}]]" not in out:
            out += f"\n- {line}"
    return out + "\n"


def sync(repo_root: Path, wiki_dir: Path, today: date, pages: dict[str, str] | None = None) -> list[str]:
    """Write the mirrored pages and the Home entries; returns the wiki files that changed."""
    pages = PAGES if pages is None else pages
    changed: list[str] = []
    for source, page in pages.items():
        new = to_wiki_page(source, (repo_root / source).read_text(encoding="utf-8"), page, today)
        path = wiki_dir / f"{page}.md"
        if not path.exists() or path.read_text(encoding="utf-8") != new:
            path.write_text(new, encoding="utf-8")
            changed.append(path.name)
    home = wiki_dir / "Home.md"
    old = home.read_text(encoding="utf-8") if home.exists() else "Welcome to the opslm wiki!\n\n## Pages\n"
    new_home = update_home(old)
    if new_home != old:
        home.write_text(new_home, encoding="utf-8")
        changed.append(home.name)
    return changed


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m opslm.wiki_sync", description=__doc__.split("\n\n")[0])
    p.add_argument("--push", action="store_true", help="commit and push the changes to the wiki")
    p.add_argument("--wiki-dir", help="an existing clone of the wiki (default: clone to a temp dir)")
    p.add_argument("--repo-root", default=".", help="the repository root (default: current directory)")
    args = p.parse_args(argv)

    root = Path(args.repo_root).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        wiki = Path(args.wiki_dir) if args.wiki_dir else Path(tmp) / "wiki"
        if not wiki.exists():
            subprocess.run(["git", "clone", "-q", WIKI_GIT_URL, str(wiki)], check=True)
        changed = sync(root, wiki, date.today())
        if not changed:
            print("wiki is already up to date")
            return 0
        print("changed:", ", ".join(changed))
        print(_git("diff", "--stat", cwd=wiki) or "(new files)")
        if not args.push:
            print("dry run: re-run with --push to publish")
            return 0
        for key in ("user.name", "user.email"):  # commit as the repository's configured author
            _git("config", key, _git("config", key, cwd=root).strip(), cwd=wiki)
        _git("add", "-A", cwd=wiki)
        _git("commit", "-q", "-m", "Sync status and decisions pages from the repository docs\n\n"
             "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>", cwd=wiki)
        print(_git("push", "origin", "HEAD", cwd=wiki) or "pushed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
