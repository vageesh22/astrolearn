"""Offline geocoder: a local GeoNames-derived database plus spatial timezone lookup.

Implements the Layer 2 LocationResolver protocol with no network access of any
kind. Place data comes from a SQLite database built by ``tools/geodata``; the
timezone comes from ``timezonefinder``, which carries its boundary data in the
package. Nothing here opens a socket, and the test suite enforces that.
"""
