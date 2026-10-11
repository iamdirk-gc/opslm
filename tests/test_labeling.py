import json

import pytest

from opslm import labeling as L
from opslm.data import load_dataset
from opslm.labeling_cli import main
from opslm.schema import ReasonCode, Relationship, Split
from tests.factories import case_input, fact

RC = ReasonCode


def candidate(n, b_metric="Revenue", b_value="42.5", split=Split.TRAIN, family=None):
    return L.CandidatePair(
        input=case_input(fact(f"a{n}"), fact(f"b{n}", b_metric, b_value), f"c{n}",
                         family=family or f"s{n}"),
        source="synthetic", split=split,
    )


def spans(n):
    return f"s-a{n}, s-b{n}"


def filled(row, concept, scope, reason="synonym", refs=None, rationale="because", flag="",
           other=""):
    row = dict(row)
    n = row["case_id"][1:]
    row.update(concept_same=concept, scope_same=scope, primary_reason=reason, other_reasons=other,
               evidence_refs=spans(n) if refs is None else refs, rationale=rationale, flag=flag)
    return row


# --- sheet IO ----------------------------------------------------------------------


@pytest.mark.parametrize("ext", ["csv", "xlsx"])
def test_sheet_roundtrip_and_columns(tmp_path, ext):
    path = tmp_path / f"s.{ext}"
    cands = [candidate(1), candidate(2, b_value="44.1")]
    L.export_review_sheet(path, cands)
    rows = L.read_sheet(path)
    assert [r["case_id"] for r in rows] == ["c1", "c2"]
    assert rows[0]["A_metric"] == "Revenue" and rows[0]["A_value"].startswith("42.5 (= 42,500,000")
    assert rows[0]["A_evidence"] == "[s-a1] Revenue  42.5" and rows[0]["document_family"] == "s1"
    assert rows[0]["values_agree"] == "yes" and rows[1]["values_agree"] == "no"
    assert set(L.REVIEWER_COLS) <= set(rows[0]) and rows[0]["concept_same"] == ""


@pytest.mark.parametrize("ext", ["csv", "xlsx"])
def test_formula_text_from_documents_is_neutralized(tmp_path, ext):
    path = tmp_path / f"s.{ext}"
    L.export_review_sheet(path, [candidate(1, b_metric='=HYPERLINK("http://evil","x")')])
    cell = L.read_sheet(path)[0]["B_metric"]
    assert not cell.startswith("=") and "HYPERLINK" in cell


def test_safe_keeps_negative_numbers():
    assert L._safe("-12.5") == "-12.5" and L._safe("-cmd") == "'-cmd" and L._safe("+1x") == "'+1x"


def test_xlsx_has_dropdowns_and_shading(tmp_path):
    from openpyxl import load_workbook

    path = tmp_path / "s.xlsx"
    L.export_review_sheet(path, [candidate(1)])
    ws = load_workbook(path).worksheets[0]
    assert ws.freeze_panes == "B2"
    assert len(ws.data_validations.dataValidation) == 3


# --- import validation -------------------------------------------------------------


def test_valid_rows_become_reviews():
    cands = [candidate(1), candidate(2, "ARR", "39.2"), candidate(3, b_value="44.1")]
    rows = L.review_rows(cands)
    rows[0] = filled(rows[0], "yes", "yes")
    rows[1] = filled(rows[1], "no", "yes", "definition_mismatch", "s-b2")
    rows[2] = filled(rows[2], "Yes", " YES ", "Value_Mismatch", "s-a3 s-b3", other="synonym")
    res = L.import_review_sheet(rows, cands, "gerry")
    assert res.problems == [] and len(res.reviews) == 3
    assert res.reviews[2].reasons == ("value_mismatch", "synonym")
    assert res.reviews[2].evidence_refs == ("s-a3", "s-b3")
    assert [L.derived_label(c, r) for c, r in zip(cands, res.reviews, strict=True)] == [
        Relationship.EQUIVALENT, Relationship.RELATED_BUT_DIFFERENT, Relationship.CONFLICTING]


def test_blank_rows_are_unlabeled_not_errors():
    cands = [candidate(1), candidate(2)]
    rows = L.review_rows(cands)
    rows[0] = filled(rows[0], "yes", "yes")
    res = L.import_review_sheet(rows, cands, "g")
    assert res.unlabeled == ["c2"] and not res.problems


@pytest.mark.parametrize(
    "kwargs,fragment",
    [
        ({"concept": "maybe", "scope": "yes"}, "concept_same is 'maybe'"),
        ({"concept": "", "scope": "yes", "rationale": "x"}, "concept_same is 'blank'"),
        ({"concept": "yes", "scope": "yes", "reason": ""}, "primary_reason is required"),
        ({"concept": "no", "scope": "yes", "reason": "bogus"}, "unknown reason 'bogus'"),
        ({"concept": "no", "scope": "yes", "other": "definition_mismatch, nope"}, "unknown reason 'nope'"),
        ({"concept": "no", "scope": "yes", "refs": ""}, "evidence_refs is required"),
        ({"concept": "no", "scope": "yes", "refs": "s-a1, s-zz"}, "unknown evidence_refs ['s-zz']"),
        ({"concept": "yes", "scope": "yes", "rationale": ""}, "rationale is required"),
    ],
)
def test_problems_are_plain_language_with_row_numbers(kwargs, fragment):
    cands = [candidate(1)]
    row = filled(L.review_rows(cands)[0], kwargs.pop("concept"), kwargs.pop("scope"), **kwargs)
    res = L.import_review_sheet([row], cands, "g")
    assert res.reviews == [] and len(res.problems) >= 1
    assert res.problems[0].startswith("row 2 (c1):") and fragment in " ".join(res.problems)


def test_label_follows_computed_values_not_reviewer_opinion():
    # same concept and scope but numbers disagree: the label is conflicting, and the reviewer
    # is told so
    cands = [candidate(1, b_value="44.1")]
    row = filled(L.review_rows(cands)[0], "yes", "yes", reason="")
    assert "give 'conflicting'" in L.import_review_sheet([row], cands, "g").problems[0]


def test_insufficient_evidence_needs_no_evidence_refs():
    cands = [candidate(1)]
    row = filled(L.review_rows(cands)[0], "cannot_tell", "yes", "missing_definition", refs="")
    res = L.import_review_sheet([row], cands, "g")
    assert res.problems == [] and res.reviews[0].evidence_refs == ()


def test_unknown_and_duplicate_case_ids():
    cands = [candidate(1)]
    row = filled(L.review_rows(cands)[0], "yes", "yes")
    ghost = dict(row, case_id="nope")
    res = L.import_review_sheet([row, row, ghost], cands, "g")
    assert any("appears more than once" in p for p in res.problems)
    assert any("unknown case_id 'nope'" in p for p in res.problems)


def test_edits_to_readonly_columns_are_ignored():
    cands = [candidate(1)]
    row = filled(L.review_rows(cands)[0], "yes", "yes")
    row["B_value"] = "9999"
    review = L.import_review_sheet([row], cands, "g").reviews[0]
    assert L.derived_label(cands[0], review) == Relationship.EQUIVALENT


# --- batches and agreement ---------------------------------------------------------


def test_plan_batches_overlap_split_and_determinism():
    cands = [candidate(i) for i in range(20)]
    plan = L.plan_batches(cands, ["gerry", "partner"], overlap=6, seed=1)
    a, b = set(plan["gerry"]), set(plan["partner"])
    assert len(a & b) == 6 and a | b == {c.case_id for c in cands}
    assert len(plan["gerry"]) == 6 + 7 and len(plan["partner"]) == 6 + 7
    assert plan == L.plan_batches(cands, ["gerry", "partner"], overlap=6, seed=1)
    assert plan["gerry"] != plan["partner"]


def test_plan_batches_rejects_bad_input():
    cands = [candidate(i) for i in range(3)]
    with pytest.raises(ValueError, match="exceeds"):
        L.plan_batches(cands, ["a", "b"], overlap=9)
    with pytest.raises(ValueError, match="two distinct"):
        L.plan_batches(cands, ["a", "a"], overlap=1)


def test_cohen_kappa_known_values():
    assert L.cohen_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    assert L.cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == 0.0
    assert L.cohen_kappa(["a", "a"], ["a", "a"]) is None
    assert L.cohen_kappa([], []) is None


def rev(case_id, reviewer, concept, scope, reason=RC.SYNONYM, refs=None, flag=""):
    n = case_id[1:]
    return L.Review(case_id=case_id, reviewer=reviewer, concept_same=concept, scope_same=scope,
                    reasons=(reason,), evidence_refs=refs or (f"s-a{n}", f"s-b{n}"),
                    rationale="r", flag=flag)


def test_compare_reviews_finds_disagreements_and_flags():
    cands = [candidate(1), candidate(2, "ARR", "39.2"), candidate(3, "Gross Revenue", "42.5")]
    a = [rev("c1", "A", True, True), rev("c2", "A", False, True, RC.DEFINITION_MISMATCH),
         rev("c3", "A", None, True, RC.MISSING_DEFINITION, flag="unsure")]
    b = [rev("c1", "B", True, True), rev("c2", "B", False, True, RC.DEFINITION_MISMATCH),
         rev("c3", "B", False, True, RC.DEFINITION_MISMATCH)]
    ag = L.compare_reviews(a, b, cands)
    assert ag.n == 3 and ag.disagreements == ["c3"] and ag.flagged == ["c3"]
    assert ag.label_agreement == pytest.approx(2 / 3)
    only_a = L.compare_reviews(a[:1], b, cands)
    assert only_a.n == 1  # only the shared cases count


def test_disagreement_sheet_and_resolution_roundtrip(tmp_path):
    cands = [candidate(1), candidate(2, "Gross Revenue", "42.5")]
    a = [rev("c1", "A", True, True), rev("c2", "A", None, True, RC.MISSING_DEFINITION)]
    b = [rev("c1", "B", True, True), rev("c2", "B", False, True, RC.DEFINITION_MISMATCH)]
    ag = L.compare_reviews(a, b, cands)
    path = tmp_path / "adj.xlsx"
    L.export_disagreement_sheet(path, a, b, cands, ag)
    rows = L.read_sheet(path)
    assert [r["case_id"] for r in rows] == ["c2"] and rows[0]["r1_reviewer"] == "A"
    assert rows[0]["r2_concept_same"] == "no" and rows[0]["why"] == "disagree"

    rows[0].update(resolved_concept_same="no", resolved_scope_same="yes",
                   resolved_primary_reason="definition_mismatch", resolved_evidence_refs="s-b2",
                   resolved_rationale="Gross is a different measure.")
    missing_rule = L.import_resolutions(rows, cands)
    assert missing_rule.reviews == [] and "rule_decided is required" in missing_rule.problems[0]
    rows[0]["rule_decided"] = "Gross vs net revenue are different concepts"
    ok = L.import_resolutions(rows, cands)
    assert ok.problems == [] and ok.reviews[0].reviewer == L.RESOLVER


# --- finalize ----------------------------------------------------------------------


def test_finalize_agreement_resolution_and_unresolved():
    cands = [candidate(1), candidate(2, "Gross Revenue", "42.5"), candidate(3), candidate(4)]
    a = [rev("c1", "A", True, True), rev("c2", "A", None, True, RC.MISSING_DEFINITION),
         rev("c3", "A", True, True)]
    b = [rev("c1", "B", True, True), rev("c2", "B", False, True, RC.DEFINITION_MISMATCH)]
    res = [rev("c2", L.RESOLVER, False, True, RC.DEFINITION_MISMATCH)]
    out = L.finalize(cands, [a, b], res)
    assert {c.case_id for c in out.cases} == {"c1", "c2", "c3"} and out.problems == []
    assert out.unlabeled == ["c4"]
    c2 = next(c for c in out.cases if c.case_id == "c2")
    assert c2.gold.relationship == Relationship.RELATED_BUT_DIFFERENT and c2.human_labeled
    assert c2.gold.labeled_by == "A, B" and c2.gold.reviewed_by == L.RESOLVER
    c1 = next(c for c in out.cases if c.case_id == "c1")
    assert (c1.gold.labeled_by, c1.gold.reviewed_by) == ("A", "B")
    c3 = next(c for c in out.cases if c.case_id == "c3")
    assert (c3.gold.labeled_by, c3.gold.reviewed_by) == ("A", None)

    unresolved = L.finalize(cands, [a, b], [])
    assert any("c2" in p and "disagree" in p for p in unresolved.problems)


def test_finalize_checks_leakage():
    c1, c2 = candidate(1), candidate(2, split=Split.TEST, family="s1")  # same family in train and test
    out = L.finalize([c1, c2], [[rev("c1", "A", True, True), rev("c2", "A", True, True)]])
    assert any("spans multiple splits" in p for p in out.problems)


# --- command line, end to end ---------------------------------------------------------


def test_cli_end_to_end(tmp_path, capsys):
    cands = [candidate(i, b_value="44.1" if i % 2 else "42.5") for i in range(1, 9)]
    cpath = tmp_path / "cands.jsonl"
    L.write_candidates(cpath, cands)
    out = tmp_path / "out"
    assert main(["plan", "--candidates", str(cpath), "--reviewers", "gerry", "partner",
                 "--overlap", "4", "--out-dir", str(out), "--format", "csv"]) == 0
    assert json.loads((out / "plan.json").read_text())

    def fill(name, disagree_on=None):
        rows = L.read_sheet(out / f"sheet_{name}.csv")
        by_id = {c.case_id: c for c in cands}
        for r in rows:
            c = by_id[r["case_id"]]
            conflict = r["values_agree"] == "no"
            concept = "no" if r["case_id"] == disagree_on else "yes"
            refs = spans(r["case_id"][1:])
            if concept == "no":
                r.update(concept_same="no", scope_same="yes", primary_reason="definition_mismatch",
                         evidence_refs=refs, rationale="diff concept")
            elif conflict:
                r.update(concept_same="yes", scope_same="yes", primary_reason="value_mismatch",
                         evidence_refs=refs, rationale="values differ")
            else:
                r.update(concept_same="yes", scope_same="yes", primary_reason="synonym",
                         evidence_refs=refs, rationale="same")
            assert c
        L.write_sheet(out / f"filled_{name}.csv", rows, L.REVIEW_COLUMNS)

    shared = set(json.loads((out / "plan.json").read_text())["gerry"]) & set(
        json.loads((out / "plan.json").read_text())["partner"])
    contested = min(shared)
    fill("gerry")
    fill("partner", disagree_on=contested)
    for name in ("gerry", "partner"):
        assert main(["import", "--candidates", str(cpath), "--sheet", str(out / f"filled_{name}.csv"),
                     "--reviewer", name, "--out", str(out / f"{name}.jsonl")]) == 0
    capsys.readouterr()
    assert main(["agreement", "--candidates", str(cpath), "--a", str(out / "gerry.jsonl"),
                 "--b", str(out / "partner.jsonl"), "--out", str(out / "adj.csv")]) == 0
    assert "1 disagreement" in capsys.readouterr().out

    assert main(["finalize", "--candidates", str(cpath),
                 "--reviews", str(out / "gerry.jsonl"), str(out / "partner.jsonl"),
                 "--out", str(out / "d.jsonl")]) == 1  # unresolved disagreement blocks it

    rows = L.read_sheet(out / "adj.csv")
    rows[0].update(resolved_concept_same="yes", resolved_scope_same="yes",
                   resolved_primary_reason="synonym" if rows[0]["values_agree"] == "yes"
                   else "value_mismatch",
                   resolved_evidence_refs=spans(rows[0]["case_id"][1:]),
                   resolved_rationale="settled", rule_decided="synonyms are the same concept")
    L.write_sheet(out / "adj_filled.csv", rows, L.DISAGREEMENT_COLUMNS)
    assert main(["resolutions", "--candidates", str(cpath), "--sheet", str(out / "adj_filled.csv"),
                 "--out", str(out / "res.jsonl")]) == 0
    assert main(["finalize", "--candidates", str(cpath),
                 "--reviews", str(out / "gerry.jsonl"), str(out / "partner.jsonl"),
                 "--resolutions", str(out / "res.jsonl"), "--out", str(out / "d.jsonl")]) == 0
    final = load_dataset(out / "d.jsonl")
    assert len(final) == 8
    settled = next(c for c in final if c.case_id == rows[0]["case_id"])
    assert settled.gold.adjudication_note == "synonyms are the same concept"
