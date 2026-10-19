from datetime import date

from opslm import wiki_sync as W

TODAY = date(2026, 10, 18)
PAGES = {"docs/status.md": "Status", "docs/decisions.md": "Decisions-for-the-Project-Owner"}


def test_links_between_mirrored_pages_become_wiki_links():
    text = "See [the decisions](decisions.md) and [one item](decisions.md#a-blocking)."
    out = W.rewrite_links(text, "docs/status.md", PAGES)
    assert "(Decisions-for-the-Project-Owner)" in out
    assert "(Decisions-for-the-Project-Owner#a-blocking)" in out


def test_links_to_other_repo_files_point_at_github():
    out = W.rewrite_links("[scope](extraction-adapter-scope.md#4-choosing-the-parser) and "
                          "[readme](../README.md) and [dir](../schemas/)", "docs/status.md", PAGES)
    assert f"({W.REPO_URL}/blob/main/docs/extraction-adapter-scope.md#4-choosing-the-parser)" in out
    assert f"({W.REPO_URL}/blob/main/README.md)" in out
    assert f"({W.REPO_URL}/tree/main/schemas)" in out


def test_external_and_same_page_links_and_code_blocks_are_untouched():
    text = "[a](https://example.com/x.md) [b](#section) [c](mailto:x@y.z)\n```\n[d](docs/status.md)\n```\n"
    assert W.rewrite_links(text, "docs/status.md", PAGES) == text


def test_the_title_is_dropped_only_when_the_wiki_already_shows_it():
    same = W.to_wiki_page("docs/decisions.md", "# Decisions for the Project Owner\n\nBody.\n",
                          "Decisions-for-the-Project-Owner", TODAY)
    assert same.startswith("Body.")
    differs = W.to_wiki_page("docs/status.md", "# Status: 2026-10-18\n\nBody.\n", "Status", TODAY)
    assert differs.startswith("# Status: 2026-10-18")


def test_a_footer_names_the_source_and_says_not_to_edit_the_page():
    out = W.to_wiki_page("docs/status.md", "# Status\n\nBody.\n", "Status", TODAY)
    assert out.endswith("\n")
    assert f"{W.REPO_URL}/blob/main/docs/status.md" in out and "2026-10-18" in out
    assert "not this page" in out


def test_home_gets_each_page_once():
    home = "Welcome!\n\n## Pages\n\n- [[OpsLM v1 Metric Set]]: the metrics\n"
    once = W.update_home(home)
    assert "[[Status]]" in once and "[[Decisions for the Project Owner]]" in once
    assert W.update_home(once) == once  # idempotent
    assert once.startswith(home.rstrip("\n"))  # existing entries untouched


def test_sync_writes_pages_and_reports_only_real_changes(tmp_path):
    repo, wiki = tmp_path / "repo", tmp_path / "wiki"
    (repo / "docs").mkdir(parents=True)
    wiki.mkdir()
    (repo / "docs/status.md").write_text("# Status\n\nSee [d](decisions.md).\n")
    (repo / "docs/decisions.md").write_text("# Decisions for the Project Owner\n\nText.\n")
    (wiki / "Home.md").write_text("Welcome\n\n## Pages\n")

    first = W.sync(repo, wiki, TODAY)
    assert sorted(first) == ["Decisions-for-the-Project-Owner.md", "Home.md", "Status.md"]
    assert "(Decisions-for-the-Project-Owner)" in (wiki / "Status.md").read_text()
    assert W.sync(repo, wiki, TODAY) == []  # nothing to do the second time

    (repo / "docs/decisions.md").write_text("# Decisions for the Project Owner\n\nChanged.\n")
    assert W.sync(repo, wiki, TODAY) == ["Decisions-for-the-Project-Owner.md"]


def test_a_file_name_label_on_a_mirrored_page_becomes_the_page_title():
    out = W.rewrite_links("See [decisions.md](decisions.md#a) and [the log](decisions.md).",
                          "docs/status.md", PAGES)
    assert "[Decisions for the Project Owner](Decisions-for-the-Project-Owner#a)" in out
    assert "[the log](Decisions-for-the-Project-Owner)" in out  # a human label is kept


def test_a_file_name_label_on_a_github_link_is_kept():
    out = W.rewrite_links("[board-alignment.md](board-alignment.md)", "docs/status.md", PAGES)
    assert out == f"[board-alignment.md]({W.REPO_URL}/blob/main/docs/board-alignment.md)"
