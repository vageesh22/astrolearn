"""Time package: two distinct layers, one per module.

``local_time`` is Layer 3: a local civil date, time and IANA timezone
identifier become an exact aware-UTC instant. ``julian_day`` is Layer 4: an
exact UTC instant becomes a Julian Day in UT. Both are pure stdlib and neither
knows anything about the ephemeris.
"""
