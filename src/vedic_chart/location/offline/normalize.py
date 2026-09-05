"""Name normalization, shared by the importer and the query path.

There is exactly one definition of "the same name" in this system, and it lives
here. The importer normalizes every name it stores with these functions and the
resolver normalizes every query with them, so a query can only match what the
importer actually wrote. Any divergence between the two would produce silent
misses that no test of either side alone would catch.
"""

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
# Punctuation stripped from the ends of a token. Interior punctuation is kept:
# "Sant Ravidas Nagar" and "Wilkes-Barre" must stay distinguishable.
_EDGE_PUNCTUATION = ".,;:!?'\"`()[]{}<>/\\|-_*#"


def normalize_name(value: str) -> str:
    """Reduce a place name or query token to its comparison form.

    Casefolds, decomposes to NFKD and drops combining marks so that "Jalandhar"
    matches "Jālandhar", collapses whitespace runs, and strips surrounding
    punctuation. Deliberately not a transliterator: non-Latin scripts are left
    as they are, because GeoNames alternate names supply the Devanagari and
    Gurmukhi forms directly and they should match on their own terms.
    """
    if not isinstance(value, str):
        return ""

    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        ch for ch in decomposed if not unicodedata.combining(ch)
    )
    folded = unicodedata.normalize("NFKC", without_marks).casefold()
    collapsed = _WHITESPACE.sub(" ", folded).strip()
    return collapsed.strip(_EDGE_PUNCTUATION).strip()


def split_query(query: str) -> tuple[str, list[str]]:
    """Split "City, Qualifier, Qualifier" into a place token and qualifiers.

    The first comma-separated part is the place; everything after it is a
    qualifier to be matched against country, admin1 and admin2 names. Empty
    parts are discarded, so "Delhi,,India" behaves like "Delhi, India".
    """
    parts = [normalize_name(part) for part in query.split(",")]
    parts = [part for part in parts if part]
    if not parts:
        return "", []
    return parts[0], parts[1:]
