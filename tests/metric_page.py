"""Parser for docs/metric-set-v1.md, shared by the tests that keep code and page consistent."""

from pathlib import Path

DOC = Path("docs/metric-set-v1.md")
METRIC_IDS = {"Revenue": "revenue", "ARR": "arr", "Gross margin": "gross_margin",
              "Adjusted EBITDA": "adjusted_ebitda", "Net income": "net_income"}


def split_items(text: str) -> list[str]:
    """Split a ';' separated list, ignoring semicolons inside parentheses."""
    items, depth, current = [], 0, ""
    for ch in text:
        depth += (ch == "(") - (ch == ")")
        if ch == ";" and depth == 0:
            items.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        items.append(current.strip())
    return items


def sections() -> dict[str, dict[str, list[str]]]:
    """metric heading -> {'variants': [...], 'related': [...]}."""
    out: dict[str, dict[str, list[str]]] = {}
    current = None
    for line in DOC.read_text().splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            out[current] = {"variants": [], "related": []}
        elif current and line.startswith("- **Naming variants:**"):
            out[current]["variants"] = split_items(line.split(":**", 1)[1])
        elif current and line.startswith("- **Related but different (never merge):**"):
            out[current]["related"] = split_items(line.split(":**", 1)[1])
    return {k: v for k, v in out.items() if v["variants"]}
