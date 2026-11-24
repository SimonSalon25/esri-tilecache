# Methodology

This document states what the package does, why, and how each claim is verified. It is written so that the
results can be reproduced and criticised.

## 1. Origin

The package was extracted from *Lesná mapa*, a desktop GIS application for Slovak forestry. The trigger was a
national forest map distributed by a state agency as a single `.tpk` of several GB (one level of about 1 m/px,
512 px PNG tiles, S-JTSK [JTSK03]), stored as **Compact Cache V1**, which GDAL does not read. The map itself is not
part of this repository; the tests use public Esri samples and synthetic caches.

## 2. Storage layouts

Compact V2 and the tile package formats are documented by Esri (github.com/Esri/raster-tiles-compactcache,
github.com/Esri/tile-package-spec, Apache 2.0). For Compact V1 Esri gives only a conceptual description (a separate
`.bundlx` index next to each `.bundle`), not the byte layout; its layout was established on the national cache and
confirmed by the tests:

| | V1 | V2 |
|---|---|---|
| index | separate `.bundlx`: 16-byte header + 128 × 128 records of 5 bytes | inside `.bundle`: 64-byte header + 128 × 128 records of 8 bytes |
| record | offset into `.bundle`; tile = 4-byte length + image | low 40 bits offset, high 24 bits length |
| order | **column-major** (`i = column · 128 + row`) | **row-major** (`i = row · 128 + column`) |
| empty tile | offset < 60, or length 0 | length 0 |

*How column-major was established:* decoded neighbouring tiles of the national cache join seamlessly only in
column-major order (lines and labels continue across tile edges; checked on sample tiles supplied by the author).
The test suite builds both layouts synthetically and a mutation (V1 read row-major) is caught.

*Reading:* uncompressed ZIP members are read directly from disk at their data offset. On Python 3.12,
`ZipFile.open(...).seek()` after reading another member returned data from a wrong position (observed on the
national cache: `EOFError` at bundle 21 and garbled tiles); reading directly avoids it and is faster.

*Result on the national cache (user's PC, November 2026):* 329,907 tiles converted in 39 s (3.8 GB GeoPackage);
overviews ×4…×1024 built in 12.5 min; the map opens in the application in 0.7 s.

*Other open-source readers (checked 24 November 2026).* GDAL's ESRIC driver reads Compact V2 and `.tpkx` with
256 px tiles and states that V1 `.tpk` is not supported. tpkutils (github.com/consbio/tpkutils, ISC, last release
0.8.2 in 2022) reads V1 `.tpk` into MBTiles or loose tiles, but requires Web Mercator; according to its README it
does not write GeoPackage and does not handle other coordinate systems or Compact V2. tpk2gpkg (github.com/cuulee/tpk2gpkg) converts `.tpkx` and
`.vtpk`, not V1. What this package adds is therefore not the first V1 reader, but V1 (and V2) in any coordinate
system and tile size, written as a GeoPackage that keeps the source tiles and levels unchanged, with LERC and
overviews.

## 3. Tile matrix of the GeoPackage

The GeoPackage tile matrix follows what GDAL writes: level Z has a 2^Z × 2^Z matrix whose top-left corner lies on
the Esri tile grid, so every source tile maps to exactly one GeoPackage tile and no tile is resampled. The real
data extent (from the tile indexes, not from tile data) goes to `gpkg_contents`, from which GDAL derives the raster
size. Multi-level caches are kept as far as the levels form a chain with a resolution ratio of exactly 2 from the
finest level up; coarser source levels become overviews with their original bytes. A table
`esri_tilecache_source_levels` records which levels are source data so that overview building never overwrites or
deletes them.

## 4. Overviews

Overviews are built from the tiles themselves on threads (each target tile from f × f source tiles, then 2 × 2),
with premultiplied-alpha averaging (no dark fringes at data edges). For a single-level map the first overview is
×4 (a line map with text is still readable at ×2 from the base level; skipping it saves most of the time and
space); below several source levels and for elevation it is ×2. While building, the file is in WAL journal mode
(on Windows, many reader threads otherwise blocked the writer: "database is locked"); afterwards it returns to the
default mode so the GeoPackage stays one file. An interrupted build deletes all overviews.

## 5. Elevation (LERC)

LERC tiles are decoded with the `lerc` package and written as one-band float32 TIFF tiles of an OGC 17-066r1 2D
gridded coverage; the LERC mask becomes NoData (−9999). Tiles of size t + 1 (Esri elevation caches overlap the
neighbour by one row and column) are cropped to t. **This was verified only on synthetic caches**; on a real
elevation package the half-pixel position should be checked against known points. Elevation overviews are the
mean of valid values; a block with no valid value is NoData.

## 6. Vector tiles (.vtpk → MBTiles)

MBTiles prescribes Web Mercator and the XYZ grid with TMS row order. A `.vtpk` is accepted only if its tiling is
exactly that grid (origin at the top-left corner of the Web Mercator world, resolution × tile size × 2^z = equator
length); Esri levels then equal XYZ levels. Tiles are copied as they are (gzip-compressed MVT); layer names and
attribute types for the `vector_layers` metadata are read from the tiles with a minimal protobuf parser. Other
CRSs are refused with an explanation (QGIS reads such a `.vtpk` directly).

## 7. Invalid and damaged tiles

A tile whose length points beyond the end of the bundle, or that cannot be read completely, is skipped and counted
as *damaged*. An image tile without a PNG or JPEG signature is skipped and counted as *invalid*. Esri's own sample
`Usa.tpkx` contains such tiles: in levels 0 and 1 the first four bytes of the PNG signature are missing (the data
start with `0D 0A 1A 0A`); this was confirmed on the original bundle. If a whole coarse level is invalid, it is
not treated as source data and the overview builder computes it.

## 8. Verification

| claim | how it is tested |
|---|---|
| tiles are not re-encoded | GeoPackage blobs compared byte by byte with the source tiles |
| tiles are at the right place | GDAL (rasterio) reads windows of the GeoPackage and compares them pixel by pixel with the decoded source; geotransform compared with the cache origin |
| V1 / V2 / exploded layouts | synthetic caches built by the tests from the layouts in section 2 |
| real-world files | Esri sample caches (Compact V2 folder, `.tpkx`) — every valid tile found at its place |
| LERC | values within `maxZError` (0.01 m), NoData in the masked hole, overview = mean of valid values |
| MBTiles | tile bytes, TMS rows, metadata; GDAL's MVT driver reads the points at the expected coordinates |
| robustness | cancellation leaves no file, damaged tile counted, existing target untouched |
| the tests themselves | `tools/mutations.py` introduces 16 deliberate bugs one at a time; the suite must fail for each |
