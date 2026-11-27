"""Couverture du sol : correspondance des classes, parts, lecteur GeoTIFF et ordre de grandeur de la forêt."""

from __future__ import annotations

import json
import math
import struct
import tempfile
import unittest
from pathlib import Path

from pipeline.core import landcover as L
from pipeline.core.geotiff import TiledTiff, lzw_decode
from pipeline.sources.nrcan_landcover import CLASSES

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web" / "data"
INTERIM = ROOT / "data" / "interim"


def lzw_encode(data: bytes) -> bytes:
    """TIFF LZW encoder (test helper): MSB first, « early change », clear code at the start and when the table is
    full. The decoder adds its table entries one code later than the encoder, hence the widths below."""
    out = bytearray()
    bits = nbits = 0
    width = 9

    def put(code):
        nonlocal bits, nbits
        bits = (bits << width) | code
        nbits += width
        while nbits >= 8:
            nbits -= 8
            out.append((bits >> nbits) & 0xFF)
        bits &= (1 << nbits) - 1

    table = {bytes([i]): i for i in range(256)}
    nxt = 258
    put(256)
    w = b""
    for b in data:
        wc = w + bytes([b])
        if wc in table:
            w = wc
            continue
        put(table[w])
        table[wc] = nxt
        nxt += 1
        if nxt >= 4094:
            put(256)
            table = {bytes([i]): i for i in range(256)}
            nxt, width = 258, 9
        elif nxt >= (1 << width):
            width += 1
        w = bytes([b])
    if w:
        put(table[w])
        if nxt >= (1 << width) - 1 and width < 12:
            width += 1
    put(257)
    if nbits:
        out.append((bits << (8 - nbits)) & 0xFF)
    return bytes(out)


class ClassMappingTest(unittest.TestCase):
    def test_every_nalcms_class_is_mapped(self):
        self.assertEqual(set(L.NALCMS), set(CLASSES))
        self.assertEqual(sorted(CLASSES), [1, 2, 5, 6, 8, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19])
        ids = {t["id"] for t in L.COVER_TABLE}
        for k, (cid, group) in L.NALCMS.items():
            self.assertIn(group, L.GROUPS, k)
            self.assertIn(cid, ids, k)

    def test_groups(self):
        self.assertEqual(sorted(L.FOREST_CLASSES), [1, 2, 5, 6])
        self.assertEqual(L.NALCMS[15][1], "crop")
        self.assertEqual(L.NALCMS[14][1], "wetland")
        self.assertEqual(L.NALCMS[17][1], "developed")
        self.assertEqual(L.NALCMS[18], (0, "water"))

    def test_shares_sum_to_one_and_dominant_ignores_water(self):
        cnt = {18: 120, 1: 50, 5: 20, 15: 10, 0: 999}  # 0 = hors des données, ignoré
        s = L.shares(cnt)
        self.assertAlmostEqual(sum(s.values()), 1.0)
        self.assertAlmostEqual(s[18], 0.6)
        g = L.group_shares(cnt)
        self.assertAlmostEqual(sum(g.values()), 1.0)
        self.assertAlmostEqual(g["forest"], 0.35)
        self.assertEqual(L.dominant_cover(cnt), 2)  # conifères, pas l'eau
        self.assertEqual(L.dominant_cover({18: 5}), 0)
        self.assertEqual(L.shares({0: 3}), {})

    def test_hex_counts_with_identity_projection(self):
        pts = L.LandcoverPoints.__new__(L.LandcoverPoints)
        pts.x0, pts.y0, pts.dx, pts.dy, pts.w, pts.h = 0.5, 9.5, 1.0, 1.0, 10, 10
        pts.data = bytes([1] * 50 + [15] * 49 + [0])
        counts = L.hex_counts(pts, lambda x, y: (x, y), lambda x, y: 0 if x < 5 else 1, block=4)
        self.assertEqual(sum(sum(c.values()) for c in counts.values()), 99)
        self.assertEqual(counts[0][1] + counts[1][1], 50)


class GeoTiffTest(unittest.TestCase):
    def test_lzw_round_trip(self):
        data = bytes((i * 7 // 13) % 19 for i in range(70000)) + bytes(5000) + bytes(range(256)) * 20
        self.assertEqual(lzw_decode(lzw_encode(data)), data)

    def test_tiled_tiff(self):
        # A 32 × 16 image in two 16 × 16 tiles, the second LZW-compressed.
        t0 = bytes(range(256))
        t1 = bytes((255 - i) for i in range(256))
        t1z = lzw_encode(t1)
        entries = [(256, 3, 1, 32), (257, 3, 1, 16), (258, 3, 1, 8), (259, 3, 1, 5), (277, 3, 1, 1),
                   (322, 3, 1, 16), (323, 3, 1, 16)]
        n = len(entries) + 2
        ifd_off = 8
        data_off = ifd_off + 2 + n * 12 + 4
        tiles_off = data_off + 16
        t0z = lzw_encode(t0)
        offs = (tiles_off, tiles_off + len(t0z))
        cnts = (len(t0z), len(t1z))
        body = struct.pack("<2I", *offs) + struct.pack("<2I", *cnts)
        ent = entries + [(324, 4, 2, data_off), (325, 4, 2, data_off + 8)]
        ent.sort()
        ifd = struct.pack("<H", len(ent))
        for tag, typ, cnt, val in ent:
            ifd += struct.pack("<HHI", tag, typ, cnt) + (struct.pack("<HH", val, 0) if typ == 3 else struct.pack("<I", val))
        ifd += struct.pack("<I", 0)
        blob = b"II" + struct.pack("<HI", 42, ifd_off) + ifd + body + t0z + t1z
        with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as f:
            f.write(blob)
        tif = TiledTiff(f.name)
        lvl = tif.levels[0]
        self.assertEqual((lvl.width, lvl.height, lvl.tiles_across), (32, 16, 2))
        self.assertEqual(tif.read_tile(lvl, 0, 0), t0)
        self.assertEqual(tif.read_tile(lvl, 1, 0), t1)
        tif.close()
        Path(f.name).unlink()


class MapCoverTest(unittest.TestCase):
    def test_every_quebec_hex_has_a_cover(self):
        w = json.loads((WEB / "world.json").read_text())
        qc = [i for i, o in enumerate(w["owner"]) if o >= 0]
        self.assertTrue(all(w["cover"][i] > 0 for i in qc))
        ids = {t["id"] for t in w["tables"]["cover"]}
        self.assertTrue(set(w["cover"]) <= ids)

    def test_cover_lenses(self):
        doc = json.loads((WEB / "lenses.json").read_text())
        ids = {l["id"] for l in doc["lenses"]}
        self.assertTrue({"forest", "farmland", "wetland", "developed"} <= ids)
        w = json.loads((WEB / "world.json").read_text())
        tot = None
        for lid in ("forest", "farmland", "wetland", "developed"):
            vals = json.loads((WEB / "lenses" / f"{lid}.json").read_text())["values"]
            for i, o in enumerate(w["owner"]):
                if o >= 0:
                    self.assertTrue(0 <= vals[i] <= 1, (lid, i))
            tot = vals if tot is None else [a + b if a is not None else None for a, b in zip(tot, vals)]
        self.assertTrue(all(v <= 1.0 + 0.002 for v in tot if v is not None))  # quatre valeurs arrondies au millième

    @unittest.skipUnless((INTERIM / "_world.json").exists(), "data/interim absent (lancer pipeline build)")
    def test_hex_shares_sum_to_one(self):
        cc = json.loads((INTERIM / "_world.json").read_text())["data"]["cover_counts"]
        for c, cnt in list(cc.items())[::50]:
            g = L.group_shares({int(k): v for k, v in cnt.items()})
            self.assertAlmostEqual(sum(g.values()), 1.0, places=9, msg=c)

    def test_forest_share_is_close_to_the_published_figure(self):
        # MRNF, « Chiffres-clés du Québec forestier – Édition 2026 » : forêts de plus de 901 503 km² ; milieu terrestre
        # (terre et eau douce, sans le milieu marin) de 1 512 206 km² ; soit 59,6 %.
        # https://cdn-contenu.quebec.ca/cdn-contenu/forets/documents/entreprises/RA_chiffres-cles_forets_MRNF.pdf
        # Ici : la part des points en forêt (NALCMS 1, 2, 5, 6) sur les hexagones du Québec, eau comprise. Les deux
        # définitions diffèrent (le MRNF compte comme forêt les coupes et brûlis en régénération, que la couverture
        # du sol classe en arbustaie, et une partie de la forêt claire du Nord) : on n'attend qu'un ordre de grandeur.
        published = 901_503 / 1_512_206
        w = json.loads((WEB / "world.json").read_text())
        vals = json.loads((WEB / "lenses" / "forest.json").read_text())["values"]
        qc = [vals[i] for i, o in enumerate(w["owner"]) if o >= 0]
        share = sum(qc) / len(qc)  # hexagones de même superficie
        self.assertLess(abs(share - published), 0.12, (share, published))
        hex_km2 = 3 * math.sqrt(3) / 2 * 25
        forest_km2 = sum(qc) * hex_km2
        self.assertTrue(0.7 * 901_503 < forest_km2 < 1.1 * 901_503, forest_km2)


if __name__ == "__main__":
    unittest.main()
