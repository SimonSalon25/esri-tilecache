"""Tests of esri-tilecache. Every test also has a mutation check (tools/mutations.py): the code is broken on
purpose and the suite must fail — a test that passes on broken code guards nothing.

1. headers of .tpk V1/V2, an exploded folder, a LERC .tpkx and a .vtpk;
2. .tpk V1 and V2 → GeoPackage: GDAL reads every tile pixel by pixel as the original, at the right place,
   tiles are byte-identical (no re-encoding), a missing tile is transparent;
3. exploded folder → GeoPackage;
4. two Esri levels: the coarse one is a ×2 overview with the original bytes, the pyramid continues below and
   never overwrites source levels;
5. Esri samples (Apache 2.0): all valid tiles byte for byte at their place; invalid tiles counted and rebuilt;
6. LERC elevation → float32 gridded coverage within the LERC error, hole = NoData, mean-value pyramid;
7. .vtpk → MBTiles: MVT bytes, TMS rows, metadata, style; GDAL reads points at the right place; non-Web
   Mercator refused;
8. cancellation leaves no partial file; damaged tile counted; an existing target is never overwritten.
"""
from __future__ import annotations

import gzip
import io
import json
import sqlite3
import zipfile

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.windows import Window

import esri_tilecache as etc
import synthetic as s


def _rgba(b: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(b)).convert("RGBA")).transpose(2, 0, 1)


def _blob(path, table, z, c, r):
    con = sqlite3.connect(path)
    try:
        x = con.execute(f'SELECT tile_data FROM "{table}" WHERE zoom_level=? AND tile_column=? AND tile_row=?',
                        (z, c, r)).fetchone()
    finally:
        con.close()
    return None if x is None else bytes(x[0])


def test_1_headers(tmp_path):
    for v2 in (False, True):
        s.tpk(tmp_path / f"t{v2}.tpk", v2)
        with etc.open_cache(tmp_path / f"t{v2}.tpk") as c:
            assert c.storage == ("V2" if v2 else "V1") and c.kind == "tpk" and c.content == "image"
            assert c.epsg == 8353 and c.tile_size == 512 and c.format == "PNG"
            assert abs(c.levels[0] - s.RES) < 1e-12 and c.origin_x == s.OX and c.origin_y == s.OY
            assert "Sample map" in c.description and "Test" in c.rights and c.title == "Test map"
            assert c.bundles[0][1:3] == (s.R0, s.C0)
            assert "EPSG:8353" in c.summary() and "bundles of the finest level: 1" in c.summary()
    s.exploded(tmp_path / "exp")
    with etc.open_cache(tmp_path / "exp" / "Layers" / "conf.xml") as c:
        assert c.storage == "exploded" and c.kind == "folder" and len(c.exploded[0]) == 8
    s.tpkx_lerc(tmp_path / "dem.tpkx")
    with etc.open_cache(tmp_path / "dem.tpkx") as c:
        assert c.kind == "tpkx" and c.content == "lerc" and c.epsg == 8353 and c.rights == "© test"
    s.vtpk(tmp_path / "v.vtpk")
    with etc.open_cache(tmp_path / "v.vtpk") as c:
        assert c.kind == "vtpk" and c.content == "mvt" and c.epsg == 3857 and c.tile_size == 512
        assert c.style is not None and c.levels_with_tiles() == [0, 1, 2]
    (tmp_path / "none.tpk").write_bytes(b"not a zip")
    with pytest.raises(etc.TileCacheError):
        etc.open_cache(tmp_path / "none.tpk")


@pytest.mark.parametrize("v2", [False, True])
def test_2_tpk_to_geopackage(tmp_path, v2):
    tiles = s.tpk(tmp_path / "t.tpk", v2)
    r = etc.to_geopackage(tmp_path / "t.tpk", tmp_path / "t.gpkg", "map")
    assert r["tiles"] == len(tiles) and r["damaged"] == 0
    assert r["width"] == 8 * 512 and r["height"] == 8 * 512 and r["epsg"] == 8353
    with rasterio.open(tmp_path / "t.gpkg") as ds:
        step = 512 * s.RES
        assert abs(ds.transform.c - (s.OX + s.C0 * step)) < 1e-6
        assert abs(ds.transform.f - (s.OY - s.R0 * step)) < 1e-6
        assert abs(ds.transform.a - s.RES) < 1e-9 and ds.crs.to_epsg() == 8353
        for (rr, cc), b in tiles.items():
            assert np.array_equal(ds.read(window=Window(cc * 512, rr * 512, 512, 512)), _rgba(b)), (rr, cc)
        assert ds.read(4, window=Window(2 * 512, 2 * 512, 512, 512)).max() == 0, "missing tile must be transparent"
    z = r["gpkg_levels"][-1]
    assert _blob(tmp_path / "t.gpkg", "map", z, 5, 3) == tiles[(3, 5)], "tile must be byte-identical"


def test_3_exploded(tmp_path):
    tiles = s.exploded(tmp_path / "cache")
    r = etc.to_geopackage(tmp_path / "cache", tmp_path / "e.gpkg")
    assert r["tiles"] == 8
    with rasterio.open(tmp_path / "e.gpkg") as ds:
        assert abs(ds.transform.c - (s.OX + s.C0 * 256 * s.RES)) < 1e-6 and (ds.width, ds.height) == (768, 768)
        for (rr, cc), b in tiles.items():
            x = ds.read(window=Window((cc - s.C0) * 256, (rr - s.R0) * 256, 256, 256))
            assert np.array_equal(x, _rgba(b)), (rr, cc)
        assert ds.read(4, window=Window(256, 256, 256, 256)).max() == 0


def test_4_multi_level_and_overviews(tmp_path):
    levels = s.multi_level(tmp_path / "m.tpk", n=8)
    r = etc.to_geopackage(tmp_path / "m.tpk", tmp_path / "m.gpkg", "map")
    assert r["esri_levels"] == [1, 0] and len(r["gpkg_levels"]) == 2
    zf, zc = r["gpkg_levels"][1], r["gpkg_levels"][0]
    assert zf == zc + 1 and r["overviews_missing"] == list(range(zc))
    assert r["tiles"] == 64 + 16
    for (rr, cc), b in levels[0].items():
        assert _blob(tmp_path / "m.gpkg", "map", zc, cc - s.C0 // 2, rr - s.R0 // 2) == b
    f = etc.build_overviews(tmp_path / "m.gpkg", threads=2)
    assert f and f[0] == 2 and f == sorted(f)
    for (rr, cc), b in levels[0].items():
        assert _blob(tmp_path / "m.gpkg", "map", zc, cc - s.C0 // 2, rr - s.R0 // 2) == b, "source level overwritten"
    assert etc.has_overviews(tmp_path / "m.gpkg", "map")
    with rasterio.open(tmp_path / "m.gpkg") as ds:
        assert ds.overviews(1)[:2] == [2, 4]
        x = ds.read(out_shape=(4, 1024, 1024))
        assert np.array_equal(x[:, :256, :256], _rgba(levels[0][(s.R0 // 2, s.C0 // 2)]))
    etc.delete_overviews(tmp_path / "m.gpkg", "map")
    assert _blob(tmp_path / "m.gpkg", "map", zc, 0, 0) == levels[0][(s.R0 // 2, s.C0 // 2)]
    assert not etc.has_overviews(tmp_path / "m.gpkg", "map")


def _all_tiles(cache):
    return {(lv, r, c): b for lv in cache.levels_with_tiles() for r, c, b in cache.tiles(lv)}


@pytest.mark.parametrize("name", ["sample_cache", "Usa.tpkx"])
def test_5_esri_samples(tmp_path, name):
    src = s.DATA / name
    with etc.open_cache(src) as c:
        original = _all_tiles(c)
        res0 = c.levels[c.finest_level]
    r = etc.to_geopackage(src, tmp_path / "x.gpkg", "sample")
    bad = {k for k, b in original.items() if not etc.is_valid_image(b)}
    assert r["tiles"] == len(original) - len(bad) and r["invalid"] == len(bad) and r["epsg"] == 3857
    if name == "Usa.tpkx":     # levels 0 and 1 of the Esri sample lack the PNG signature
        assert len(bad) == 2 and sorted({k[0] for k in bad}) == [0, 1] and r["overviews_missing"] == [0, 1]
    zmax = r["gpkg_levels"][-1]
    fine = [(rr, cc) for (lv, rr, cc) in original if lv == r["esri_levels"][0]]
    width = (max(x[1] for x in fine) - min(x[1] for x in fine) + 1) * 256
    height = (max(x[0] for x in fine) - min(x[0] for x in fine) + 1) * 256
    assert (r["width"], r["height"]) == (width, height)
    con = sqlite3.connect(tmp_path / "x.gpkg")
    x0, y1 = con.execute("SELECT min_x, max_y FROM gpkg_tile_matrix_set").fetchone()
    con.close()
    off_c = round((x0 + s.HALF_EQUATOR) / (256 * res0))
    off_r = round((s.HALF_EQUATOR - y1) / (256 * res0))
    for (lv, rr, cc), b in original.items():
        if (lv, rr, cc) in bad:
            continue
        k = r["esri_levels"].index(lv)
        assert _blob(tmp_path / "x.gpkg", "sample", zmax - k, cc - off_c // 2 ** k, rr - off_r // 2 ** k) == b
    with rasterio.open(tmp_path / "x.gpkg") as ds:
        assert ds.crs.to_epsg() == 3857 and abs(ds.res[0] - res0) < 1e-6 and (ds.width, ds.height) == (width, height)
        col = (ds.transform.c + s.HALF_EQUATOR) / (256 * res0)
        assert abs(col - round(col)) < 1e-6, "left edge off the tile grid"
    if r["overviews_missing"]:
        etc.build_overviews(tmp_path / "x.gpkg", "sample", threads=2)
    with rasterio.open(tmp_path / "x.gpkg") as ds:
        assert ds.read(out_shape=(ds.count, 64, 64)).any()


@pytest.mark.parametrize("overlap", [1, 0])
def test_6_lerc(tmp_path, overlap):
    expected = s.tpkx_lerc(tmp_path / "d.tpkx", overlap=overlap)
    r = etc.to_geopackage(tmp_path / "d.tpkx", tmp_path / "d.gpkg", "dem")
    assert r["elevation"] and r["tiles"] == 4 and (r["width"], r["height"]) == (512, 512)
    with rasterio.open(tmp_path / "d.gpkg") as ds:
        assert ds.dtypes[0] == "float32" and ds.count == 1 and ds.nodata == -9999.0
        assert ds.crs.to_epsg() == 8353 and ds.transform.c == -600000.0 and ds.transform.f == -1100000.0
        z = ds.read(1).astype(np.float64)
    for (rr, cc), arr in expected.items():
        x = z[rr * 256:(rr + 1) * 256, cc * 256:(cc + 1) * 256]
        valid = ~np.isnan(arr)
        assert np.all(x[~valid] == -9999.0), "hole must be NoData"
        assert np.abs(x[valid] - arr[valid]).max() <= 0.0100001, "error above LERC maxZError"
    con = sqlite3.connect(tmp_path / "d.gpkg")
    kind = con.execute("SELECT datatype, data_null FROM gpkg_2d_gridded_coverage_ancillary").fetchone()
    st = con.execute("SELECT count(*), min(min), max(max) FROM gpkg_2d_gridded_tile_ancillary").fetchone()
    con.close()
    assert kind == ("float", -9999.0) and st[0] == 4 and 390 < st[1] < st[2] < 1500
    etc.build_overviews(tmp_path / "d.gpkg", "dem", threads=2)               # elevation: ×2 by default
    with rasterio.open(tmp_path / "d.gpkg") as ds:
        assert ds.overviews(1) == [2]
        full = ds.read(1).astype(np.float64)
        small = ds.read(1, out_shape=(256, 256)).astype(np.float64)
    ref = np.nanmean(np.where(full == -9999.0, np.nan, full).reshape(256, 2, 256, 2), axis=(1, 3))
    assert np.isnan(ref).sum() == 9 * 24 and np.all(small[np.isnan(ref)] == -9999.0)
    ref = np.where(np.isnan(ref), -9999.0, ref)
    assert np.allclose(small, ref, atol=1e-3), "elevation overview must be the mean of valid values"


def test_6b_lerc_wrong_size(tmp_path):
    import lerc
    s.tpkx_lerc(tmp_path / "d.tpkx")
    wrong = bytes(lerc.encode(np.zeros((250, 250), dtype=np.float32), 1, False, None, 0.01, 1)[2])
    with zipfile.ZipFile(tmp_path / "d.tpkx") as z:
        root = z.read("root.json")
    with zipfile.ZipFile(tmp_path / "bad.tpkx", "w") as z:
        z.writestr("root.json", root)
        z.writestr("tile/L00/R0000C0000.bundle", s.bundle_v2({(0, 0): wrong}))
    with pytest.raises(etc.TileCacheError, match="250"):
        etc.to_geopackage(tmp_path / "bad.tpkx", tmp_path / "bad.gpkg")
    assert not (tmp_path / "bad.gpkg").exists()


def test_7_vtpk_to_mbtiles(tmp_path):
    expected = s.vtpk(tmp_path / "v.vtpk")
    r = etc.to_mbtiles(tmp_path / "v.vtpk", tmp_path / "v.mbtiles")
    assert r["tiles"] == 21 and r["xyz_levels"] == [0, 1, 2] and r["not_gzip"] == 0
    assert r["layers"] == ["forest", "roads"]
    con = sqlite3.connect(tmp_path / "v.mbtiles")
    for (z, x, y), (data, _l) in expected.items():
        b = con.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                        (z, x, y)).fetchone()
        assert b is not None and bytes(b[0]) == data, (z, x, y)
    meta = dict(con.execute("SELECT name, value FROM metadata"))
    con.close()
    assert meta["format"] == "pbf" and meta["minzoom"] == "0" and meta["maxzoom"] == "2"
    vl = {x["id"]: x for x in json.loads(meta["json"])["vector_layers"]}
    assert set(vl) == {"forest", "roads"} and vl["roads"]["minzoom"] == 2 and vl["forest"]["minzoom"] == 0
    assert vl["forest"]["fields"] == {"name": "String"}
    from pyproj import Transformer
    tr = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    ref = (*tr.transform(1800000, 6000000), *tr.transform(2500000, 6400000))
    assert max(abs(float(a) - b) for a, b in zip(meta["bounds"].split(","), ref)) < 1e-6
    assert meta["name"] == "Vector test" and meta["attribution"] == "© test"
    assert json.loads(r["style"].read_text(encoding="utf-8"))["layers"][0]["id"] == "forest"
    assert etc.mvt_layers(gzip.compress(s.mvt({"a": [(1, 1, "x")], "b": []}))) == {"a": {"name": "String"}, "b": {}}
    pyogrio = pytest.importorskip("pyogrio")
    gdf = pyogrio.read_dataframe(tmp_path / "v.mbtiles", layer="forest")
    points = dict(zip(gdf["name"], gdf.geometry))
    assert set(points) == {f"forest 2/{r}/{c}" for r in range(4) for c in range(4)}
    step = 2 * s.HALF_EQUATOR / 4
    for rr, cc in ((0, 0), (3, 1), (2, 3)):            # Esri row 0 = top (TMS is flipped)
        x = -s.HALF_EQUATOR + cc * step + (100 + 10 * cc) / 4096 * step
        y = s.HALF_EQUATOR - rr * step - (200 + 10 * rr) / 4096 * step
        p = points[f"forest 2/{rr}/{cc}"]
        assert abs(p.x - x) < step / 4096 and abs(p.y - y) < step / 4096


def test_7b_refusals(tmp_path):
    s.vtpk(tmp_path / "v.vtpk")
    s.vtpk(tmp_path / "sjtsk.vtpk", epsg=8353)          # XYZ-like grid, but not Web Mercator
    for src, dst, fn, word in ((tmp_path / "sjtsk.vtpk", tmp_path / "j.mbtiles", etc.to_mbtiles, "Web Mercator"),
                               (tmp_path / "v.vtpk", tmp_path / "v.gpkg", etc.to_geopackage, "MBTiles")):
        with pytest.raises(etc.TileCacheError, match=word):
            fn(src, dst)
        assert not dst.exists()


def test_8_cancel_damage_existing(tmp_path):
    s.tpk(tmp_path / "t.tpk", False)
    with pytest.raises(etc.Cancelled):
        etc.to_geopackage(tmp_path / "t.tpk", tmp_path / "t.gpkg", cancelled=lambda: True)
    assert not (tmp_path / "t.gpkg").exists()
    s.vtpk(tmp_path / "v.vtpk")
    with pytest.raises(etc.Cancelled):
        etc.to_mbtiles(tmp_path / "v.vtpk", tmp_path / "v.mbtiles", cancelled=lambda: True)
    assert not (tmp_path / "v.mbtiles").exists()
    s.tpk(tmp_path / "p.tpk", True, n=8)
    etc.to_geopackage(tmp_path / "p.tpk", tmp_path / "p.gpkg")
    with pytest.raises(etc.Cancelled):
        etc.build_overviews(tmp_path / "p.gpkg", threads=2, cancelled=lambda: True)
    with rasterio.open(tmp_path / "p.gpkg") as ds:
        assert ds.overviews(1) == []
    tiles = {(0, 0): s.tile_image(0), (0, 1): s.tile_image(1), (1, 0): s.tile_image(2)}
    b, bx = s.bundle_v1(tiles)
    b = bytearray(b)
    off = int.from_bytes(bx[16 + 5 * 128:21 + 5 * 128], "little")
    b[off:off + 4] = (10 ** 9).to_bytes(4, "little")    # length beyond the end of the bundle
    with zipfile.ZipFile(tmp_path / "z.tpk", "w") as z:
        z.writestr("v101/Layers/conf.xml", s.conf_xml(False))
        name = f"v101/Layers/_alllayers/L00/R{s.R0:04x}C{s.C0:04x}"
        z.writestr(name + ".bundle", bytes(b))
        z.writestr(name + ".bundlx", bx)
    r = etc.to_geopackage(tmp_path / "z.tpk", tmp_path / "z.gpkg")
    assert r["tiles"] == 2 and r["damaged"] == 1
    size = (tmp_path / "z.gpkg").stat().st_size
    with pytest.raises(etc.TileCacheError):
        etc.to_geopackage(tmp_path / "z.tpk", tmp_path / "z.gpkg")
    assert (tmp_path / "z.gpkg").stat().st_size == size
