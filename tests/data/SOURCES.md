# Esri samples used by the tests

| file | source | licence |
|---|---|---|
| `sample_cache/` | github.com/Esri/raster-tiles-compactcache, folder `sample_cache` (Compact V2, Web Mercator, L00–L02, JPEG 256 px) | Apache 2.0 (`LICENSE-raster-tiles-compactcache.txt`) |
| `Usa.tpkx` | github.com/Esri/tile-package-spec, `Sample TPKX Files/Usa.tpkx` (Web Mercator, L00–L05, PNG 256 px) | Apache 2.0 (`LICENSE-tile-package-spec.txt`) |

The files are included unchanged; each repository's licence is attached separately (© Esri).
Note: in `Usa.tpkx` the tiles of levels 0 and 1 lack the first 4 bytes of the PNG signature (they start with
`0D 0A 1A 0A`); the tests use this as a real-world example of invalid tiles.
