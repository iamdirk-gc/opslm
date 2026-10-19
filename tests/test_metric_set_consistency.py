"""Keeps the code in step with docs/metric-set-v1.md (which mirrors the project wiki page).

The variants live in several places: the generator's vocabulary, the rules baseline's synonym
table, the prompt and the docs. This test fails when the metric page names a variant the code
does not recognize, or a "never merge" metric that the code would treat as the same concept.
"""

import re
from pathlib import Path

import pytest

from opslm.baselines.rules import RulesBaseline
from opslm.datagen.vocab import metric_id_for
from tests.factories import fact

DOC = Path("docs/metric-set-v1.md")
METRIC_IDS = {"Revenue": "revenue", "ARR": "arr", "Gross margin": "gross_margin",
              "Adjusted EBITDA": "adjusted_ebitda", "Net income": "net_income"}


def _sections() -> dict[str, dict[str, list[str]]]:
    """metric heading -> {'variants': [...], 'related': [...]} parsed from the page."""
    out: dict[str, dict[str, list[str]]] = {}
    current = None
    for line in DOC.read_text().splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            out[current] = {"variants": [], "related": []}
        elif current and line.startswith("- **Naming variants:**"):
            out[current]["variants"] = [v.strip() for v in line.split(":**", 1)[1].split(";")]
        elif current and line.startswith("- **Related but different (never merge):**"):
            out[current]["related"] = [v.strip() for v in line.split(":**", 1)[1].split(";")]
    return {k: v for k, v in out.items() if v["variants"]}


def _name(item: str) -> str | None:
    """The metric name in a 'related but different' entry, or None for explanatory entries."""
    if " vs." in item:
        return None
    return re.sub(r"\s*\(.*$", "", item).strip()


def test_the_page_lists_exactly_the_metrics_the_code_knows():
    assert set(_sections()) == set(METRIC_IDS)


@pytest.mark.parametrize("heading", sorted(METRIC_IDS))
def test_every_naming_variant_maps_to_its_metric(heading):
    expected = METRIC_IDS[heading]
    rules = RulesBaseline()
    for variant in [heading, *_sections()[heading]["variants"]]:
        assert metric_id_for(variant).value == expected, f"generator maps {variant!r} elsewhere"
        a = fact("a", variant, metric_id=expected)
        b = fact("b", heading, metric_id=expected)
        core, _ = rules._parse_metric(a)
        core_heading, _ = rules._parse_metric(b)
        assert core == core_heading == expected, f"rules baseline does not recognise {variant!r}"


@pytest.mark.parametrize("heading", sorted(METRIC_IDS))
def test_never_merge_metrics_are_not_treated_as_variants(heading):
    expected = METRIC_IDS[heading]
    rules = RulesBaseline()
    for item in _sections()[heading]["related"]:
        name = _name(item)
        if not name:
            continue
        assert metric_id_for(name).value != expected, f"generator maps {name!r} to {expected}"
        concept, _ = rules._concept_same(fact("a", heading, metric_id=expected),
                                         fact("b", name, metric_id="other"))
        assert concept is not True, f"rules baseline merges {name!r} with {heading}"
