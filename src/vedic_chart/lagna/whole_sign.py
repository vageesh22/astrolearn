"""Whole Sign house assignment.

Pure module: standard library only, and no knowledge of grahas, ephemerides or
anything astronomical. It maps sign indices to house numbers and nothing else,
which is the whole of the Whole Sign scheme.

In Whole Sign houses a sign *is* a house. The sign the Lagna falls in becomes
house 1 in its entirety -- the Lagna's exact degree within the sign plays no
part -- and each following sign is the next house, counted forward through the
zodiac.
"""

RASHI_COUNT = 12


def _validate_index(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an int in 0..11; got {value!r}.")
    if not 0 <= value < RASHI_COUNT:
        raise ValueError(f"{name} must be in 0..11; got {value}.")


def house_number(rashi_index: int, lagna_rashi_index: int) -> int:
    """Return the Whole Sign house (1..12) a sign occupies for a given Lagna.

    Both arguments are 0-based rashi indices as produced by the Vedic layer.
    The Lagna's own sign always yields house 1.
    """
    _validate_index(rashi_index, "rashi_index")
    _validate_index(lagna_rashi_index, "lagna_rashi_index")

    return (rashi_index - lagna_rashi_index) % RASHI_COUNT + 1


def assign_houses(lagna_rashi_index: int, rashi_indices: dict) -> dict:
    """Map each key's rashi index to its Whole Sign house number.

    Generic over the keys, so it works equally for a dict keyed by Graha, by
    name, or by anything else the caller is tracking.
    """
    _validate_index(lagna_rashi_index, "lagna_rashi_index")

    return {
        key: house_number(rashi_index, lagna_rashi_index)
        for key, rashi_index in rashi_indices.items()
    }
