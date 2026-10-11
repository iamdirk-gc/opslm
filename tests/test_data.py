import pytest

from opslm.data import (
    DatasetError,
    dataset_hash,
    load_dataset,
    read_cases,
    validate_cases,
    write_cases,
)
from opslm.schema import CONSTRUCTION_LABELER, Split
from tests.factories import case as make_case
from tests.factories import fact


def case(n, family=None, split="train", human=False, a=None, b=None, **kw):
    """A conflicting case; generator-labeled unless ``human``."""
    return make_case(
        f"c{n}", a or fact(f"a{n}", value=f"{n}"), b or fact(f"b{n}", value=f"{n + 100}"),
        "conflicting", family=family or f"fam{n}", split=split, reasons=("value_mismatch",),
        labeled_by="gerry" if human else CONSTRUCTION_LABELER, **kw)


def test_roundtrip_and_sorted_output(tmp_path):
    path = tmp_path / "d.jsonl"
    cases = [case(2), case(1), case(3, split="test", human=True)]
    write_cases(path, cases)
    assert [c.case_id for c in read_cases(path)] == ["c1", "c2", "c3"]
    assert load_dataset(path, split=Split.TEST) == [cases[2]]


def test_clean_dataset_has_no_problems():
    assert validate_cases([case(1), case(2, split="test", human=True)]) == []


def test_parse_error_names_line(tmp_path):
    path = tmp_path / "d.jsonl"
    write_cases(path, [case(1)])
    with open(path, "a") as f:
        f.write('{"input": {"case_id": "bad"}}\n')
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


def test_document_family_spanning_splits():
    cases = [case(1, "acme", "train"), case(2, "acme", "test", human=True)]
    assert any("document family acme spans" in p for p in validate_cases(cases))


def test_fact_in_multiple_splits():
    shared = fact("shared", value="7")
    cases = [case(1, split="train", a=shared), case(2, split="test", human=True, a=shared)]
    assert any("fact shared appears in multiple splits" in p for p in validate_cases(cases))


def test_fact_id_with_conflicting_content():
    cases = [case(1, a=fact("x", value="1")), case(2, a=fact("x", value="2"))]
    assert any("different content" in p for p in validate_cases(cases))


def test_identical_pair_under_new_ids_across_splits():
    train = case(1, a=fact("a1", value="5"), b=fact("b1", value="9"))
    test = case(2, split="test", human=True, a=fact("a2", value="5"), b=fact("b2", value="9"))
    assert any("identical fact pair" in p for p in validate_cases([train, test]))


def test_identical_pair_swapped_order_detected():
    train = case(1, a=fact("a1", value="5"), b=fact("b1", value="9"))
    test = case(2, split="test", human=True, a=fact("b2", value="9"), b=fact("a2", value="5"))
    assert any("identical fact pair" in p for p in validate_cases([train, test]))


def test_generator_labels_not_allowed_in_test():
    assert any("labeled by people" in p for p in validate_cases([case(1, split="test")]))


def test_stale_guideline_version():
    stale = case(1, human=True, guideline_version="0.9")
    assert any("guideline 0.9" in p for p in validate_cases([stale]))


def test_generator_labels_with_stale_version_allowed():
    assert validate_cases([case(1, guideline_version="0.9")]) == []


def test_load_dataset_raises_with_problems(tmp_path):
    path = tmp_path / "d.jsonl"
    write_cases(path, [case(1, split="test")])
    with pytest.raises(DatasetError, match="labeled by people"):
        load_dataset(path)


def test_dataset_hash_is_order_independent_and_content_sensitive():
    a, b = case(1), case(2)
    assert dataset_hash([a, b]) == dataset_hash([b, a])
    assert dataset_hash([a, b]) != dataset_hash([a, case(2, a=fact("a2", value="99"))])
