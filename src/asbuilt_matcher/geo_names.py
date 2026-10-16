"""Conservative, auditable geographic label matching; no entity discovery."""

from difflib import SequenceMatcher
import re
import unicodedata

DIRECTIONS = {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
              "NORTHEAST": "NE", "NORTHWEST": "NW", "SOUTHEAST": "SE", "SOUTHWEST": "SW"}
SUFFIXES = {"STREET": "ST", "ROAD": "RD", "AVENUE": "AVE", "BOULEVARD": "BLVD",
            "DRIVE": "DR", "LANE": "LN", "COURT": "CT", "CIRCLE": "CIR", "PLACE": "PL",
            "PARKWAY": "PKWY", "HIGHWAY": "HWY", "TERRACE": "TER", "TRAIL": "TRL",
            "WAY": "WAY", "EXTENSION": "EXT", "COVE": "CV"}


def normalize_name(value, *, street=False):
    value = value.translate(str.maketrans({"\u2013": " ", "\u2014": " ", "\u2212": " "}))
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().upper()
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    tokens = value.split()
    if street:
        tokens = [DIRECTIONS.get(t, SUFFIXES.get(t, t)) for t in tokens]
    return " ".join(tokens)


def normalize_identifier(value, *, lot=False):
    # Keep leading zeroes and punctuation: parcel IDs are not road names.
    value = " ".join(str(value).upper().split())
    return re.sub(r"^LOT\s+", "", value) if lot else value


def match_name(query, label, *, street=False, threshold=0.86):
    """Return raw-exact, normalized or conservative fuzzy evidence, or None."""
    left, right = normalize_name(query, street=street), normalize_name(label, street=street)
    if not left or not right:
        return None
    if " ".join(query.upper().split()) == " ".join(label.upper().split()):
        return {"match_type": "exact", "similarity": 1.0, "normalized_query": left, "normalized_reference": right}
    if left == right:
        return {"match_type": "normalized", "similarity": 1.0, "normalized_query": left, "normalized_reference": right}
    # Route/phase numbers, directional qualifiers and differing suffixes must not
    # disappear in fuzzy matching. OCR digit errors require analyst correction.
    if re.findall(r"\d+", left) != re.findall(r"\d+", right):
        return None
    if street:
        direction_set = set(DIRECTIONS.values())
        a, b = set(left.split()) & direction_set, set(right.split()) & direction_set
        if a != b:
            return None
        suffix_set = set(SUFFIXES.values())
        a, b = set(left.split()) & suffix_set, set(right.split()) & suffix_set
        if a and b and a != b:
            return None
    if min(len(left.replace(" ", "")), len(right.replace(" ", ""))) < 5:
        return None
    similarity = SequenceMatcher(None, left, right, autojunk=False).ratio()
    if similarity < threshold:
        return None
    return {"match_type": "approximate", "similarity": round(similarity, 6),
            "normalized_query": left, "normalized_reference": right}
