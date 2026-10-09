from decimal import Decimal

import pytest

from opslm.data import (
    DatasetError,
    dataset_hash,
    load_dataset,
    read_cases,
    validate_cases,
    write_cases,
)
from opslm.labels import GUIDELINE_VERSION
from opslm.schema import (
    BusinessFact,
    DiscrepancyReason,
    EvalCase,
    FactPair,
    Relation,
    SourceKind,
    SourceRef,
    Split,
)


def fact(fact_id, value="1"):
    return BusinessFact(
        fact_id=fact_id,
        metric="Revenue",
        value=Decimal(value),
        unit="USD",
        source=SourceRef(document_id="d"),
    )


def case(n, scenario=None, split=Split.TRAIN, reviewed=False, a=None, b=None, **kw):
    return EvalCase(
        case_id=f"c{n}",
        scenario_id=scenario or f"s{n}",
        pair=FactPair(fact_a=a or fact(f"a{n}", f"{n}"), fact_b=b or fact(f"b{n}", f"{n + 100}")),
        label=Relation.CONFLICTING,
        concept_same=True,
        scope_same=True,
        discrepancy_reason=DiscrepancyReason.UNEXPLAINED,
        rationale="r",
        source_kind=SourceKind.SYNTHETIC,
        split=split,
        reviewed=reviewed,
        guideline_version=GUIDELINE_VERSION,
        **kw,
    )


def test_roundtrip_and_sorted_output(tmp_path):
    path = tmp_path / "d.jsonl"
    cases = [case(2), case(1), case(3, split=Split.TEST, reviewed=True)]
    write_cases(path, cases)
    assert [c.case_id for c in read_cases(path)] == ["c1", "c2", "c3"]
    assert load_dataset(path, split=Split.TEST) == [cases[2]]


def test_clean_dataset_has_no_problems():
    assert validate_cases([case(1), case(2, split=Split.TEST, reviewed=True)]) == []


def test_parse_error_names_line(tmp_path):
    path = tmp_path / "d.jsonl"
    write_cases(path, [case(1)])
    with open(path, "a") as f:
        f.write('{"case_id": "bad"}\n')
    with pytest.raises(DatasetError, match=r"d\.jsonl:2"):
        read_cases(path)


def test_blank_lines_ignored(tmp_path):
    path = tmp_path / "d.jsonl"
    write_cases(path, [case(1)])
    with open(path, "a") as f:
        f.write("\n\n")
    assert len(read_cases(path)) == 1


def test_duplicate_case_id():
    problems = validate_cases([case(1), case(1)])
    assert any("duplicate case_id" in p for p in problems)


def test_scenario_spanning_splits():
    cases = [case(1, "s", Split.TRAIN), case(2, "s", Split.TEST, reviewed=True)]
    assert any("scenario s spans" in p for p in validate_cases(cases))


def test_fact_in_multiple_splits():
    shared = fact("shared", "7")
    cases = [
        case(1, split=Split.TRAIN, a=shared),
        case(2, split=Split.TEST, reviewed=True, a=shared),
    ]
    assert any("fact shared appears in multiple splits" in p for p in validate_cases(cases))


def test_fact_id_with_conflicting_content():
    cases = [case(1, a=fact("x", "1")), case(2, a=fact("x", "2"))]
    assert any("different content" in p for p in validate_cases(cases))


def test_identical_pair_under_new_ids_across_splits():
    train = case(1, a=fact("a1", "5"), b=fact("b1", "9"))
    test = case(2, split=Split.TEST, reviewed=True, a=fact("a2", "5"), b=fact("b2", "9"))
    assert any("identical fact pair" in p for p in validate_cases([train, test]))


def test_identical_pair_swapped_order_detected():
    train = case(1, a=fact("a1", "5"), b=fact("b1", "9"))
    test = case(2, split=Split.TEST, reviewed=True, a=fact("b2", "9"), b=fact("a2", "5"))
    assert any("identical fact pair" in p for p in validate_cases([train, test]))


def test_unreviewed_test_case():
    assert any("must be reviewed" in p for p in validate_cases([case(1, split=Split.TEST)]))


def test_stale_guideline_version():
    stale = case(1, reviewed=True).model_copy(update={"guideline_version": "0.9"})
    assert any("guideline 0.9" in p for p in validate_cases([stale]))


def test_unreviewed_stale_version_allowed():
    stale = case(1).model_copy(update={"guideline_version": "0.9"})
    assert validate_cases([stale]) == []


def test_load_dataset_raises_with_problems(tmp_path):
    path = tmp_path / "d.jsonl"
    write_cases(path, [case(1, split=Split.TEST)])
    with pytest.raises(DatasetError, match="must be reviewed"):
        load_dataset(path)


def test_dataset_hash_is_order_independent_and_content_sensitive():
    a, b = case(1), case(2)
    assert dataset_hash([a, b]) == dataset_hash([b, a])
    assert dataset_hash([a, b]) != dataset_hash([a, case(2, a=fact("a2", "99"))])
