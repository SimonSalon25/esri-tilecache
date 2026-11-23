"""Mutation check: break the code on purpose, one change at a time; the test suite must fail every time.

    python tools/mutations.py            # all mutations
    python tools/mutations.py "LERC"     # only mutations whose name contains the text
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = "src/esri_tilecache/"
MUTATIONS = [
    ("V1 read row-major instead of column-major", P + "reader.py",
     "records.append((offset, i % BUNDLE_SIZE, i // BUNDLE_SIZE))", "records.append((offset, i // BUNDLE_SIZE, i % BUNDLE_SIZE))"),
    ("V2 length from the upper 32 bits", P + "reader.py", "offset, length = value & 0xFFFFFFFFFF, value >> 40",
     "offset, length = value & 0xFFFFFFFFFF, value >> 32"),
    ("V1 empty (length 0) counted into the extent", P + "reader.py", 'if struct.unpack("<I", f.read(4))[0]:', "if True:"),
    ("102100 not mapped to 3857", P + "reader.py", "return 3857 if code in WEB_MERCATOR_ALIASES else code", "return code"),
    ("MBTiles without TMS row flip", P + "mbtiles.py", "rows.append((z, c, (2 ** z - 1) - r, data))", "rows.append((z, c, r, data))"),
    ("MBTiles without the Web Mercator check", P + "mbtiles.py", "    if cache.epsg != 3857:", "    if False:"),
    ("MBTiles cancellation ignored", P + "mbtiles.py", '''                if cancelled is not None and cancelled():
                    raise Cancelled("conversion cancelled")
                z = xyz[lv]''', "                z = xyz[lv]"),
    ("vector_layers without attributes", P + "mbtiles.py", '"fields": attributes.get(m, {})', '"fields": {}'),
    ("LERC 257 cropped at the top-left", P + "lerc.py", "        arr = arr[:t, :t]\n", "        arr = arr[1:, 1:]\n"),
    ("LERC mask ignored", P + "lerc.py", "        arr[~np.asarray(mask, dtype=bool)] = data_null\n", "        pass\n"),
    ("data extent = aligned matrix", P + "convert.py", '"width_px": (d_c1 - d_c0) * t', '"width_px": (c_max - c_min) * t'),
    ("only the finest level is a source level", P + "convert.py", "record_source_levels(con, table, zoom_from)",
     'record_source_levels(con, table, m["zmax"])'),
    ("no image signature check", P + "convert.py",
     'return data[:8] == b"\\x89PNG\\r\\n\\x1a\\n" or data[:3] == b"\\xff\\xd8\\xff"', "return True"),
    ("partial GeoPackage left after an error", P + "convert.py", "            target.unlink()", "            pass"),
    ("elevation pyramid includes NoData", P + "overviews.py", "            a[a == data_null] = np.nan\n", "            pass\n"),
    ("elevation pyramid starts at ×4", P + "overviews.py", "start = 2 if is_elev else 4", "start = 4"),
]
only = sys.argv[1] if len(sys.argv) > 1 else ""
survived = 0
for name, file, old, new in MUTATIONS:
    if only not in name:
        continue
    d = Path(tempfile.mkdtemp()) / "k"
    shutil.copytree(ROOT, d, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    p = d / file
    text = p.read_text(encoding="utf-8")
    assert text.count(old) == 1, (name, text.count(old))
    p.write_text(text.replace(old, new), encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", "tests"], cwd=d,
                       capture_output=True, text=True)
    caught = r.returncode != 0
    survived += not caught
    print(("CAUGHT   " if caught else "SURVIVED ") + name, flush=True)
    shutil.rmtree(d.parent, ignore_errors=True)
sys.exit(1 if survived else 0)
