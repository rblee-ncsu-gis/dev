import pytest

from asbuilt_matcher.geo_names import match_name, normalize_identifier, normalize_name


@pytest.mark.parametrize("left,right", [
    ("North Pine Street", "N PINE ST"), ("Southwest Oak Boulevard", "SW OAK BLVD"),
    ("Cedar Avenue SE", "CEDAR AVE SOUTHEAST"), ("NC 211—Supply Road", "NC 211 SUPPLY RD"),
    ("Ocean Drive", "ocean dr."), ("Café Lane", "CAFE LN")])
def test_street_normalization(left, right):
    assert normalize_name(left, street=True) == normalize_name(right, street=True)
    assert match_name(left, right, street=True)["match_type"] in {"exact", "normalized"}


def test_fuzzy_errors_are_distinguished_from_exact_and_normalized():
    assert match_name("SUPPLY ROAD", "Supply Road", street=True)["match_type"] == "exact"
    assert match_name("Supply Rd", "Supply Road", street=True)["match_type"] == "normalized"
    assert match_name("Suppiy Road", "Supply Road", street=True)["match_type"] == "approximate"
    assert match_name("Harbor Estats", "Harbor Estates")["match_type"] == "approximate"


@pytest.mark.parametrize("left,right", [("NC 211", "NC 217"), ("North Supply Road", "South Supply Road"),
    ("North Supply Road", "Supply Road"), ("Supply Road", "Supply Court"), ("ABC", "ABD"), ("", "")])
def test_numbers_directions_suffixes_and_short_words_are_not_guessed(left, right):
    assert match_name(left, right, street=True) is None


def test_identifiers_preserve_punctuation_and_leading_zeroes():
    assert normalize_identifier(" px-001 ") == "PX-001"
    assert normalize_identifier("PX-001") != normalize_identifier("PX001")
    assert normalize_identifier("Lot 012", lot=True) == "012"
    assert normalize_identifier("012", lot=True) != normalize_identifier("12", lot=True)
