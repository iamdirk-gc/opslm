from opslm.baselines.rules import entity_same
from opslm.data import company_key
from opslm.schema import Entity
from tests.factories import fact


def test_dotted_legal_suffixes_are_one_word():
    assert company_key("Acme L.L.C.") == company_key("ACME, LLC") == "acme"
    a = fact("a", entity=Entity(name="Caldex Partners LLC"))
    b = fact("b", entity=Entity(name="CALDEX PARTNERS, L.L.C."))
    assert entity_same(a, b) is True


def test_company_key_ignores_case_punctuation_and_legal_suffix():
    assert company_key("ACME, Inc.") == company_key("Acme Corporation") == "acme"
    assert company_key("Acme & Sons Ltd") == "acme and sons"
