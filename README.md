# esri-tilecache

Convert Esri tile caches into open, standard formats — **without re-encoding a single tile**.

| input | content | output |
|---|---|---|
| `.tpk` — Compact **V1** (`.bundle` + `.bundlx`) or V2 | PNG / JPEG images | GeoPackage tiles |
| `.tpkx` | images | GeoPackage tiles |
| `.tpkx` or cache folder with **LERC** tiles | elevation | GeoPackage 2D gridded coverage (float32) |
| ArcGIS Server cache folder (`conf.xml`, also *exploded* loose tiles) | images | GeoPackage tiles |
| `.vtpk` (Web Mercator) | Mapbox vector tiles | MBTiles 1.3 (`pbf`) + the Esri style next to it |

## Problem, state of the art and solution

**Problem.** National maps are distributed as Esri tile packages. A national forest map used in our work comes from
a state agency as a single `.tpk` of several GB stored as **Compact Cache V1**. Open GIS software and mobile field
apps cannot use it directly.

**State as of 23 November 2026.** GDAL — and with it QGIS — reads `.tpkx` and Compact V2 caches, but **not the older
Compact V1 `.tpk`**, still used by some national mapping agencies; the V1 layout is not documented by Esri. The
alternatives were proprietary software or re-encoding the tiles with quality loss.

**Solution.** This package reads all of them, keeps every image tile byte for byte (no quality loss, conversion
limited only by disk speed) and writes a GeoPackage that GDAL, QGIS and mobile apps open directly; LERC elevation
caches become float32 coverages and vector tile packages MBTiles. The undocumented V1 layout is described in
[METHODOLOGY.md](METHODOLOGY.md). The QGIS plugin [Esri Tile Cache Converter](https://github.com/SimonSalon25/qgis-plugins)
offers the same conversion in QGIS.

**Aim.** National maps distributed as Esri tile packages should be usable in open GIS software and offline on
mobile devices in forest field work, without loss of quality and with an open, verifiable method.

Details:

- Any coordinate reference system (tested with S-JTSK [JTSK03], EPSG:8353, and Web Mercator).
- All levels of a multi-level cache are kept (coarser ones become ready-made overviews); a fast multi-threaded
  overview builder fills in the rest and never overwrites source tiles.
- Damaged tiles (length beyond the end of the bundle) and invalid tiles (no PNG/JPEG signature) are skipped and
  counted, not silently written.
- Pure Python + SQLite: no GDAL needed to convert (GDAL is only used by the tests to verify the result).

## Install

```bash
pip install esri-tilecache            # images
pip install "esri-tilecache[lerc]"    # + LERC elevation caches
```

## Use

```python
import esri_tilecache as etc

with etc.open_cache("map.tpk") as c:      # .tpk / .tpkx / .vtpk / folder / conf.xml / root.json
    print(c.summary())

r = etc.to_geopackage("map.tpk", "map.gpkg", progress=lambda done, total, text: print(text))
print(r["tiles"], "tiles,", r["damaged"], "damaged,", r["invalid"], "invalid")
etc.build_overviews("map.gpkg")           # ×4, ×8, … for one level; ×2 below several levels or for elevation

etc.to_mbtiles("vectors.vtpk", "vectors.mbtiles")
```

Every long operation accepts `progress(done, total, text)` and `cancelled()`; cancelling never leaves a partial
file behind, and an existing target file is never overwritten.

## How it was verified

See [METHODOLOGY.md](METHODOLOGY.md): the storage layouts, the decisions behind the tile matrix and the
overviews, and how the tests prove each claim (pixel-by-pixel comparison through GDAL, byte-by-byte comparison of
tiles, Esri's own sample caches, and a mutation check — each of 16 deliberate bugs makes the suite fail).

```bash
pip install -e ".[test]"
pytest
python tools/mutations.py
```

## How it was made

This package was written with an AI assistant, under the direction of the author, who defined the problem,
made the decisions and tested the results on real national data. What exactly the AI did and how it was
checked is in [AI_DISCLOSURE.md](AI_DISCLOSURE.md).

## Funding

Developed within the project **APVV-23-0289** *Increasing the operational reliability of linear power structures by using data from remote sensing*, supported by the Slovak Research and Development Agency (APVV).

## Licence

MIT (see `LICENSE`). The Esri sample caches in `tests/data` are © Esri, Apache 2.0 (see `tests/data/SOURCES.md`).

## Cite

See `CITATION.cff`.
