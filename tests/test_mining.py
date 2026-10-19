import json
import re

import pytest

from opslm import labeling as L
from opslm import mining as M
from opslm.mining_cli import main
from opslm.schema import Entity, EvidenceSpan, Period, SourceDocument, Split
from tests.factories import fact
from tests.metric_page import METRIC_IDS, sections

FY24 = Period(type="duration", label="FY2024", fiscal_year=2024)
DEFN = "Annualized value of active recurring subscription contracts at period end."


def doc(fid, company="Acme Corp", family="acme-fy2025"):
    return SourceDocument(doc_id=f"doc-{fid}", company=company, document_family=family, doc_type="10-K")


def corpus_of(*facts, company="Acme Corp"):
    docs = {}
    for f in facts:
        for s in f.evidence:
            docs.setdefault(s.doc_id, SourceDocument(doc_id=s.doc_id, company=company,
                                                    document_family="acme-fy2025", doc_type="10-K"))
    return M.build_corpus(facts, docs.values())


# --- classification --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "a,b,stratum",
    [
        (fact("a"), fact("b", "Sales"), M.SAME_SCOPE),
        (fact("a"), fact("b", period=FY24), M.OTHER_PERIOD),
        (fact("a"), fact("b", entity=Entity(name="Acme Corp", scope="segment", segment="Cloud")),
         M.OTHER_ENTITY),
        (fact("a", basis="gaap"), fact("b", basis="non_gaap"), M.OTHER_BASIS),
        (fact("a"), fact("b", entity=None), M.MISSING_SCOPE),
        (fact("a"), fact("b", period=None), M.MISSING_SCOPE),
        (fact("a"), fact("b", "ARR", metric_id="arr"), M.RELATED_METRIC),
        (fact("a", "Gross margin", "72", unit="percent", scale="1", metric_id="gross_margin"),
         fact("b", "Gross profit", "18", metric_id="other"), M.RELATED_METRIC),
        (fact("a"), fact("b", "Headcount", "500", unit="count", scale="1", metric_id="other"), None),
    ],
)
def test_strata(a, b, stratum):
    assert M.classify(a, b) == stratum


def test_company_defined_metrics_are_flagged_unless_both_state_the_same_definition():
    a = fact("a", "ARR", metric_id="arr", definition=DEFN)
    assert M.classify(a, fact("b", "ARR", metric_id="arr")) == M.COMPANY_DEFINED_DEFINITION
    assert M.classify(a, fact("b", "ARR", metric_id="arr", definition="Includes services.")) \
        == M.COMPANY_DEFINED_DEFINITION
    assert M.classify(a, fact("b", "ARR", metric_id="arr", definition=DEFN)) == M.SAME_SCOPE


def test_a_fact_whose_evidence_lacks_its_number_is_an_unsupported_claim():
    good = fact("a", text="Revenue  42.5")
    bad = fact("b", text="Revenue grew strongly this year")
    assert M.supported(good) and not M.supported(bad)
    assert M.classify(good, bad) == M.UNSUPPORTED


@pytest.mark.parametrize("raw,text,expected", [
    ("(5.2)", "Net loss was ($5.2 million)", True),
    ("42,481", "Total revenue  42,481", True),
    ("$42.5M", "FY2025 Sales: $42.5M", True),
    ("42.5", "Sales rose to 44.1", False),
    ("n/a", "no number here", True),
])
def test_supported(raw, text, expected):
    f = fact("a", text=text)
    f = f.model_copy(update={"quantity": f.quantity.model_copy(update={"raw_text": raw})})
    assert M.supported(f) is expected


def test_qualified_variants_are_related_to_the_metric_they_qualify():
    revenue = fact("a")
    for label in ("Core revenue", "Constant currency revenue", "Platform sales"):
        other = fact("b", label, metric_id="other")
        assert M.qualified_family(other) == "revenue" and M.related_metric(revenue, other)
    assert M.qualified_family(fact("c", "Recurring revenue", metric_id="other")) == "arr"
    assert M.qualified_family(fact("d", "Headcount", metric_id="other")) is None
    assert M.qualified_family(fact("e", "Revenue", metric_id="revenue")) is None  # already mapped
    # two different qualified variants of one metric are a subtle pair too
    assert M.related_metric(fact("x", "Core revenue", metric_id="other"),
                            fact("y", "Platform revenue", metric_id="other"))


# --- pairing ---------------------------------------------------------------------------------


def test_pairs_never_cross_companies():
    a, b = fact("a"), fact("b", "Sales")
    c = fact("c", "Revenue")
    docs = [doc("a"), doc("b"), doc("c", company="Globex Inc", family="globex-fy2025")]
    corpus = M.build_corpus([a, b, c], docs)
    keys = {p.key for p in M.enumerate_pairs(corpus)}
    assert keys == {"a|b"}


def test_facts_from_one_document_are_not_paired_unless_asked():
    a = fact("a", doc="shared")
    b = fact("b", "Sales", doc="shared")
    corpus = corpus_of(a, b)
    assert M.enumerate_pairs(corpus) == []
    assert [p.key for p in M.enumerate_pairs(corpus, cross_document_only=False)] == ["a|b"]


def test_each_pair_is_found_once_even_when_both_families_list_each_other():
    revenue, arr = fact("a"), fact("b", "ARR", metric_id="arr")
    pairs = M.enumerate_pairs(corpus_of(revenue, arr))
    assert len(pairs) == 1 and pairs[0].stratum == M.RELATED_METRIC


def test_a_corpus_must_be_consistent():
    a = fact("a")
    with pytest.raises(M.CorpusError, match="unknown document"):
        M.build_corpus([a], [])
    with pytest.raises(M.CorpusError, match="duplicate fact_id"):
        M.build_corpus([a, a], [doc("a")])
    two_docs = a.model_copy(update={"evidence": [
        a.evidence[0], EvidenceSpan(span_id="s2", doc_id="doc-other", page=2, text="Revenue 42.5")]})
    with pytest.raises(M.CorpusError, match="2 companies"):
        M.build_corpus([two_docs], [doc("a"), doc("other", company="Globex Inc", family="g")])


# --- selection ---------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def synthetic():
    from opslm.datagen.generate import generate

    run = generate(300, seed=1)
    return M.corpus_from_cases(run.train + run.validation + run.test_construction)


def test_quotas_are_respected_and_shortfalls_are_redistributed(synthetic):
    res = M.mine(synthetic, M.MiningConfig(target=120, seed=0))
    rep = res.report
    assert rep["selected"] == 120 and rep["shortfall"] == 0
    s = rep["strata"]
    assert s["unsupported_claim"]["available"] == 0 and s["unsupported_claim"]["selected"] == 0
    for name, info in s.items():
        if info["available"] >= info["quota"] and name != "same_metric_same_scope":
            assert info["selected"] == info["quota"], name
    # the unfilled unsupported_claim quota went to the heaviest stratum
    assert s["same_metric_same_scope"]["selected"] > s["same_metric_same_scope"]["quota"]
    assert sum(v["selected"] for v in s.values()) == 120


def test_no_company_or_fact_dominates(synthetic):
    cfg = M.MiningConfig(target=100, seed=0, max_company_share=0.05, max_fact_reuse=1)
    res = M.mine(synthetic, cfg)
    assert max(res.report["per_company"].values()) <= 5
    used = [f.fact_id for c in res.candidates for f in (c.input.fact_a, c.input.fact_b)]
    assert len(used) == len(set(used))  # no fact appears twice


def test_a_target_larger_than_the_pool_reports_the_shortfall():
    a, b = fact("a"), fact("b", "Sales")
    res = M.mine(corpus_of(a, b), M.MiningConfig(target=50, fractions=(0.0, 0.0, 1.0)))
    assert res.report["selected"] == 1 and res.report["shortfall"] == 49


def test_selection_is_deterministic_and_seed_dependent(synthetic):
    ids = lambda r: [c.case_id for c in r.candidates]
    a = M.mine(synthetic, M.MiningConfig(target=60, seed=3))
    b = M.mine(synthetic, M.MiningConfig(target=60, seed=3))
    c = M.mine(synthetic, M.MiningConfig(target=60, seed=4))
    assert ids(a) == ids(b) and ids(a) != ids(c)


def test_unknown_strata_are_rejected(synthetic):
    with pytest.raises(ValueError, match="unknown strata"):
        M.mine(synthetic, M.MiningConfig(weights={"bogus": 1.0}))


# --- splits and candidates -------------------------------------------------------------------


def test_splits_are_assigned_per_company_and_cover_every_requested_split():
    companies = [f"company {i}" for i in range(10)]
    a = M.assign_splits(companies, (0.5, 0.1, 0.4), seed=0)
    assert a == M.assign_splits(companies, (0.5, 0.1, 0.4), seed=0)
    assert a != M.assign_splits(companies, (0.5, 0.1, 0.4), seed=1)
    counts = {s: sum(1 for v in a.values() if v == s) for s in Split}
    assert counts == {Split.TRAIN: 5, Split.VALIDATION: 1, Split.TEST: 4}
    few = M.assign_splits(["x", "y", "z"], (0.5, 0.1, 0.4), seed=0)
    assert set(few.values()) == set(Split)  # one company each, none of the splits left empty
    assert set(M.assign_splits(["x", "y"], (0.5, 0.0, 0.5), seed=0).values()) == {Split.TRAIN, Split.TEST}
    with pytest.raises(ValueError):
        M.assign_splits(companies, (0.5, 0.5, 0.5), seed=0)


def test_candidates_keep_each_company_in_one_split_and_families_apart(synthetic):
    res = M.mine(synthetic, M.MiningConfig(target=150, seed=0))
    company_split, family_split = {}, {}
    for c in res.candidates:
        for d in c.input.documents:
            assert company_split.setdefault(company_key(d.company), c.split) == c.split
            assert family_split.setdefault(d.document_family, c.split) == c.split
    assert {c.source for c in res.candidates} == {"real"}
    assert all({"mined"} <= set(c.tags) and len(c.tags) == 2 for c in res.candidates)
    assert len({c.case_id for c in res.candidates}) == len(res.candidates)


def test_pair_order_carries_no_information(synthetic):
    res = M.mine(synthetic, M.MiningConfig(target=200, seed=0))
    first_is_lexically_smaller = sum(c.input.fact_a.fact_id < c.input.fact_b.fact_id
                                     for c in res.candidates)
    assert 0.3 < first_is_lexically_smaller / len(res.candidates) < 0.7


def test_candidates_feed_the_labeling_workflow(synthetic, tmp_path):
    res = M.mine(synthetic, M.MiningConfig(target=40, seed=0))
    path = tmp_path / "candidates.jsonl"
    L.write_candidates(path, res.candidates)
    again = L.read_candidates(path)
    assert [c.case_id for c in again] == sorted(c.case_id for c in res.candidates)
    L.export_review_sheet(tmp_path / "sheet.xlsx", again[:10])
    assert len(L.read_sheet(tmp_path / "sheet.xlsx")) == 10


# --- the miner against labels it never saw -------------------------------------------------------


def test_strata_line_up_with_the_gold_labels_of_synthetic_data():
    from opslm.datagen.generate import generate

    run = generate(300, seed=2)
    cases = run.train + run.validation + run.test_construction
    mined = {p.key: p.stratum for p in M.enumerate_pairs(M.corpus_from_cases(cases))}

    def key(c):
        return "|".join(sorted((c.input.fact_a.fact_id, c.input.fact_b.fact_id)))

    found = [c for c in cases if key(c) in mined]
    assert len(found) / len(cases) > 0.97  # the miner finds almost every pair worth labeling
    related = {"same_metric_other_period", "same_metric_other_basis", "same_metric_other_entity"}
    for c in found:
        s = mined[key(c)]
        if s in related:
            assert c.gold.relationship == "related_but_different", s
        if s == "missing_scope":
            assert c.gold.relationship == "insufficient_evidence"


# --- consistency with the metric page ------------------------------------------------------------


def test_related_families_cover_the_metric_pages_never_merge_lists():
    for heading, content in sections().items():
        metric = METRIC_IDS[heading]
        for item in content["related"]:
            if " vs." in item:
                continue  # an explanation, not a metric name
            name = M._norm(re.sub(r"\s*\(.*$", "", item))
            assert name in M.RELATED_FAMILIES[metric], f"{name!r} missing for {metric}"


# --- command line ------------------------------------------------------------------------------


def test_cli_on_a_facts_file(synthetic, tmp_path):
    facts, docs = tmp_path / "facts.jsonl", tmp_path / "documents.jsonl"
    facts.write_text("".join(f.model_dump_json() + "\n" for f in synthetic.facts))
    docs.write_text("".join(d.model_dump_json() + "\n" for d in synthetic.documents.values()))
    out, rep = tmp_path / "cands.jsonl", tmp_path / "report.json"
    assert main(["--facts", str(facts), "--documents", str(docs), "--out", str(out),
                 "--report", str(rep), "--target", "50"]) == 0
    assert len(L.read_candidates(out)) == 50
    report = json.loads(rep.read_text())
    assert report["selected"] == 50 and report["miner_version"] and report["corpus"]["facts"]


def test_cli_synthetic_dry_run_and_weight_override(tmp_path, capsys):
    out = tmp_path / "cands.jsonl"
    assert main(["--synthetic", "80", "--out", str(out), "--target", "30",
                 "--weight", "related_metric=0"]) == 0
    cands = L.read_candidates(out)
    assert cands and all(c.source == "synthetic" for c in cands)
    assert "related_metric" not in {t for c in cands for t in c.tags}
    assert "selected" in capsys.readouterr().out


def test_cli_rejects_missing_input_and_unknown_weights(tmp_path):
    with pytest.raises(SystemExit):
        main(["--out", str(tmp_path / "x.jsonl")])
    with pytest.raises(SystemExit):
        main(["--synthetic", "10", "--out", str(tmp_path / "x.jsonl"), "--weight", "bogus=1"])
