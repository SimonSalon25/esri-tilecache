# Changelog

## 0.1.1 — 2026-11-24
Documentation and testing only; the conversion is unchanged.
- State of the art corrected: tpkutils (open source) reads Compact V1 `.tpk` in Web Mercator into MBTiles; what this
  package adds is V1/V2 in any coordinate system and tile size, as a GeoPackage, with LERC and overviews
  (METHODOLOGY section 2).
- Install from GitHub (not on PyPI yet); tests run on GitHub Actions (Linux, Windows; Python 3.10, 3.13).
- AI_DISCLOSURE: the model used in each session was not recorded.

## 0.1.0 — 2026-11-22
First public version, translated from the Slovak module `lesna_jadro.dlazdice` 0.2.0 of the Lesná mapa
applications: `.tpk` Compact V1/V2, `.tpkx`, cache folders (also exploded), LERC elevation, `.vtpk` → MBTiles,
multi-threaded overviews. 13 tests, 16 mutations caught.
