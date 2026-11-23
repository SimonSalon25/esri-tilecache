"""Synthetic Esri caches for the tests: .tpk V1/V2, an exploded folder, a LERC .tpkx and an MVT .vtpk.

Layouts follow the public Esri specifications (Apache 2.0): raster-tiles-compactcache (V2: 64-byte header +
8-byte records, row-major) and tile-package-spec (root.json, tile/, iteminfo.json); Compact V1 (16-byte
.bundlx header + 5-byte records, column-major) as verified on a national cache (METHODOLOGY.md).
The image caches use a typical national tiling scheme: S-JTSK [JTSK03] (EPSG:8353), about 1 m/px, 512 px PNG.
"""
from __future__ import annotations

import gzip
import io
import json
import struct
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

RES = 1.0043272568364014
OX, OY = -33699630.645263568, 33666130.584619708
R0, C0 = 0x10880, 0xFC80
DATA = Path(__file__).resolve().parent / "data"
HALF_EQUATOR = 20037508.342787001


def tile_image(k: int, palette: bool = False, px: int = 512, fmt: str = "PNG") -> bytes:
    im = Image.new("RGB", (px, px), "white")
    d = ImageDraw.Draw(im)
    for i in range(0, px, 37 + k):
        d.line([(i, 0), (px - 1 - i // 2, px - 1)], fill=(k * 40 % 256, 60, 0), width=2)
    d.text((20 + k, px // 3), f"{k}a", fill="black")
    if palette:
        im = im.convert("P", palette=Image.ADAPTIVE, colors=16)
    b = io.BytesIO()
    im.save(b, fmt)
    return b.getvalue()


def conf_xml(v2: bool | None, *, levels=((0, RES),), px: int = 512, fmt: str = "PNG", epsg: int = 8353,
             ox: float = OX, oy: float = OY) -> str:
    storage = "esriMapCacheStorageModeExploded" if v2 is None else \
        f"esriMapCacheStorageModeCompact{'V2' if v2 else ''}"
    lods = "".join(f"<LODInfo><LevelID>{lv}</LevelID><Scale>{r * 96 / 0.0254!r}</Scale><Resolution>{r!r}</Resolution>"
                   "</LODInfo>" for lv, r in levels)
    return (f"<CacheInfo><TileCacheInfo><SpatialReference><WKID>{epsg}</WKID><LatestWKID>{epsg}</LatestWKID>"
            f"</SpatialReference><TileOrigin><X>{ox!r}</X><Y>{oy!r}</Y></TileOrigin><TileCols>{px}</TileCols>"
            f"<TileRows>{px}</TileRows><LODInfos>{lods}</LODInfos></TileCacheInfo><TileImageInfo>"
            f"<CacheTileFormat>{fmt}</CacheTileFormat></TileImageInfo><CacheStorageInfo><StorageFormat>"
            f"{storage}</StorageFormat></CacheStorageInfo></CacheInfo>")


def bundle_v1(tiles: dict) -> tuple[bytes, bytes]:
    bundle = bytearray(60)
    empty = len(bundle)
    bundle += b"\0\0\0\0"
    bx = bytearray(16) + bytearray(5 * 16384)
    for i in range(16384):
        bx[16 + 5 * i:21 + 5 * i] = empty.to_bytes(5, "little")
    for (r, c), b in tiles.items():
        i = c * 128 + r                                  # V1: column-major
        off = len(bundle)
        bundle += struct.pack("<I", len(b)) + b
        bx[16 + 5 * i:21 + 5 * i] = off.to_bytes(5, "little")
    return bytes(bundle), bytes(bx)


def bundle_v2(tiles: dict) -> bytes:
    idx = bytearray(8 * 16384)
    data = bytearray()
    base = 64 + len(idx)
    for (r, c), b in tiles.items():
        struct.pack_into("<Q", idx, 8 * (r * 128 + c), (base + len(data)) | (len(b) << 40))   # V2: row-major
        data += b
    return bytes(64) + bytes(idx) + bytes(data)


PATTERN = {(0, 0): 0, (0, 1): 1, (1, 0): 2, (3, 5): 3, (7, 7): 4}


def tpk(path: Path, v2: bool, n: int | None = None) -> dict:
    """Single-level .tpk in S-JTSK [JTSK03]; returns {(row, col) inside the bundle: bytes}."""
    tiles = {rc: tile_image(k, palette=(k % 2 == 1)) for rc, k in PATTERN.items()}
    if n:
        tiles = {(r, c): tile_image((r + c) % 5, palette=bool((r * c) % 2)) for r in range(n) for c in range(n)}
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("esriinfo/iteminfo.xml", "<ESRI_ItemInformation><title>Test map</title><description>"
                   "&lt;P&gt;Sample map&lt;/P&gt;</description>"
                   "<accessinformation>© Test 2025</accessinformation></ESRI_ItemInformation>")
        z.writestr("v101/Layers/conf.xml", conf_xml(v2))
        name = f"v101/Layers/_alllayers/L00/R{R0:04x}C{C0:04x}"
        if v2:
            z.writestr(name + ".bundle", bundle_v2(tiles))
        else:
            b, bx = bundle_v1(tiles)
            z.writestr(name + ".bundle", b)
            z.writestr(name + ".bundlx", bx)
    return tiles


def multi_level(path: Path, n: int = 8) -> dict:
    """.tpk V2 with levels L00 (2·RES) and L01 (RES); returns {level: {(row, col) absolute: bytes}}."""
    fine = {(R0 + r, C0 + c): tile_image((r * 3 + c) % 7, px=256) for r in range(n) for c in range(n)}
    coarse = {(R0 // 2 + r, C0 // 2 + c): tile_image(10 + r + c, px=256) for r in range(n // 2) for c in range(n // 2)}
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("v101/Layers/conf.xml", conf_xml(True, levels=((0, 2 * RES), (1, RES)), px=256))
        for lv, t in ((0, coarse), (1, fine)):
            per_bundle: dict = {}
            for (r, c), b in t.items():
                per_bundle.setdefault((r // 128 * 128, c // 128 * 128), {})[(r % 128, c % 128)] = b
            for (rr, cc), tiles in per_bundle.items():
                z.writestr(f"v101/Layers/_alllayers/L{lv:02d}/R{rr:04x}C{cc:04x}.bundle", bundle_v2(tiles))
    return {0: coarse, 1: fine}


def exploded(folder: Path, n: int = 3) -> dict:
    """Cache folder with loose tiles `_alllayers/L00/R%08x/C%08x.png`; tile (1, 1) is missing."""
    tiles = {(R0 + r, C0 + c): tile_image(r + 2 * c, px=256) for r in range(n) for c in range(n) if (r, c) != (1, 1)}
    (folder / "Layers").mkdir(parents=True)
    (folder / "Layers" / "conf.xml").write_text(conf_xml(None, px=256), encoding="utf-8")
    for (r, c), b in tiles.items():
        p = folder / "Layers" / "_alllayers" / "L00" / f"R{r:08x}" / f"C{c:08x}.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b)
    return tiles


# ------------------------------------------------------------------ elevation .tpkx (LERC)

def elevation_tile(k: int, t: int = 256, overlap: int = 1, hole: bool = False) -> tuple[bytes, np.ndarray]:
    """LERC tile (t+overlap)² with heights ~400–1500 m; returns (blob, expected t×t part with NaN in the hole)."""
    import lerc
    n = t + overlap
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    z = (400 + 3 * k + 0.37 * xx + 1.9 * yy + 25 * np.sin(xx / 17.0)).astype(np.float32)
    mask = np.ones((n, n), dtype=bool)
    if hole:
        mask[11:30, 41:90] = False          # odd edges → mixed blocks in the overviews
    blob = bytes(lerc.encode(z, 1, True, mask, 0.01, 1)[2])
    expected = z[:t, :t].astype(np.float64).copy()
    expected[~mask[:t, :t]] = np.nan
    return blob, expected


def tpkx_lerc(path: Path, *, overlap: int = 1) -> dict:
    """Elevation .tpkx (EPSG:8353, 256 px, LERC) with 4 tiles; returns {(row, col): expected array}."""
    t, res = 256, 5.0
    ox, oy = -600000.0, -1100000.0
    expected, tiles = {}, {}
    for (r, c, k) in ((0, 0, 0), (0, 1, 1), (1, 0, 2), (1, 1, 3)):
        blob, arr = elevation_tile(k, t, overlap, hole=(k == 2))
        tiles[(r, c)] = blob
        expected[(r, c)] = arr
    root = {"tileImageInfo": {"format": "LERC", "compressionQuality": 0, "bandCount": 1, "lercError": 0.01},
            "name": "DEM test", "tileBundlesPath": "./tile",
            "spatialReference": {"wkid": 8353, "latestWkid": 8353},
            "tileInfo": {"rows": t, "cols": t, "dpi": 96, "origin": {"x": ox, "y": oy},
                         "spatialReference": {"wkid": 8353, "latestWkid": 8353},
                         "lods": [{"level": 0, "resolution": res, "scale": res * 96 / 0.0254}]},
            "fullExtent": {"xmin": ox, "ymin": oy - 2 * t * res, "xmax": ox + 2 * t * res, "ymax": oy},
            "storageInfo": {"storageFormat": "esriMapCacheStorageModeCompactV2", "packetSize": 128}}
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("root.json", json.dumps(root))
        z.writestr("esriinfo/iteminfo.json", json.dumps({"title": "DEM test", "accessInformation": "© test"}))
        z.writestr("tile/L00/R0000C0000.bundle", bundle_v2(tiles))
    return expected


# ------------------------------------------------------------------ vector .vtpk (MVT)

def _varint(v: int) -> bytes:
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        out.append(b | (0x80 if v else 0))
        if not v:
            return bytes(out)


def _field(number: int, wtype: int, content) -> bytes:
    key = _varint(number << 3 | wtype)
    if wtype == 0:
        return key + _varint(content)
    return key + _varint(len(content)) + content


def _zz(v: int) -> int:
    return (v << 1) ^ (v >> 31)


def mvt(layers: dict) -> bytes:
    """MVT 2 tile: {layer_name: [(x, y, name), …]} — points in tile coordinates 0–4096, attribute `name`."""
    tile = b""
    for lname, points in layers.items():
        layer = _field(15, 0, 2) + _field(1, 2, lname.encode()) + _field(3, 2, b"name")
        for i, (x, y, _n) in enumerate(points):
            geom = b"".join(_varint(v) for v in (9, _zz(x), _zz(y)))
            layer += _field(2, 2, _field(1, 0, i + 1) + _field(2, 2, _varint(0) + _varint(i)) + _field(3, 0, 1)
                            + _field(4, 2, geom))
        for _x, _y, n in points:
            layer += _field(4, 2, _field(1, 2, n.encode()))
        layer += _field(5, 0, 4096)
        tile += _field(3, 2, layer)
    return tile


def vtpk(path: Path, *, epsg: int = 3857, ox: float = -HALF_EQUATOR, oy: float = HALF_EQUATOR) -> dict:
    """.vtpk with levels 0–2 (512 px); returns {(z, x, y_tms): (gzip bytes, [layer names])}."""
    lods = [{"level": z, "resolution": 2 * HALF_EQUATOR / (512 * 2 ** z), "scale": 0} for z in range(3)]
    root = {"name": "Vector test", "type": "indexedVector", "tiles": ["tile/{z}/{y}/{x}.pbf"],
            "tileInfo": {"rows": 512, "cols": 512, "dpi": 96, "format": "pbf", "origin": {"x": ox, "y": oy},
                         "spatialReference": ({"wkid": 102100} if epsg == 3857          # legacy Esri code only
                                              else {"wkid": epsg, "latestWkid": epsg}),
                         "lods": lods},
            "fullExtent": {"xmin": 1800000, "ymin": 6000000, "xmax": 2500000, "ymax": 6400000}}
    out = {}
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("p12/root.json", json.dumps(root))
        z.writestr("p12/resources/styles/root.json", json.dumps({"version": 8, "layers": [{"id": "forest"}]}))
        z.writestr("esriinfo/iteminfo.json", json.dumps({"title": "Vector test", "accessInformation": "© test"}))
        for lv in range(3):
            n = 2 ** lv
            tiles = {}
            for r in range(n):
                for c in range(n):
                    layers = {"forest": [(100 + 10 * c, 200 + 10 * r, f"forest {lv}/{r}/{c}")]}
                    if lv == 2:
                        layers["roads"] = [(2048, 2048, "road")]
                    data = gzip.compress(mvt(layers), mtime=0)
                    tiles[(r, c)] = data
                    out[(lv, c, n - 1 - r)] = (data, sorted(layers))
            z.writestr(f"p12/tile/L{lv:02d}/R0000C0000.bundle", bundle_v2(tiles))
    return out
