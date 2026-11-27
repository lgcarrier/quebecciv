"""Lecture des fichiers de formes de l'Atlas du Canada (bibliothèque standard) et projection conique de Lambert."""

from __future__ import annotations

import struct
import unittest

from pipeline.build.world import channel, components
from pipeline.core.hexgrid import HexGrid
from pipeline.sources.atlas_water import LambertConformalConic, read_dbf, read_shp_polygons


def polygon_shp(rings):
    pts = [p for r in rings for p in r]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    parts, k = [], 0
    for r in rings:
        parts.append(k)
        k += len(r)
    body = struct.pack("<i4d2i", 5, min(xs), min(ys), max(xs), max(ys), len(rings), len(pts))
    body += struct.pack(f"<{len(parts)}i", *parts) + b"".join(struct.pack("<2d", *p) for p in pts)
    rec = struct.pack(">2i", 1, len(body) // 2) + body
    header = struct.pack(">7i", 9994, 0, 0, 0, 0, 0, (100 + len(rec)) // 2) + struct.pack("<2i", 1000, 5) + bytes(64)
    return header + rec


class ShapefileTest(unittest.TestCase):
    def test_polygon_with_hole(self):
        outer = [(0, 0), (0, 10), (10, 10), (10, 0), (0, 0)]
        hole = [(4, 4), (6, 4), (6, 6), (4, 6), (4, 4)]
        recs = list(read_shp_polygons(polygon_shp([outer, hole])))
        self.assertEqual(len(recs), 1)
        bbox, rings = recs[0]
        self.assertEqual(bbox, (0.0, 0.0, 10.0, 10.0))
        self.assertEqual([len(r) for r in rings], [5, 5])
        self.assertEqual(rings[1][0], (4.0, 4.0))

    def test_dbf(self):
        fields = [(b"NAME", b"C", 12), (b"TYPE", b"C", 16)]
        rl = 1 + sum(f[2] for f in fields)
        hl = 32 + 32 * len(fields) + 1
        head = struct.pack("<4BIHH20x", 3, 126, 1, 1, 1, hl, rl)
        desc = b"".join(n.ljust(11, b"\0") + t + bytes(4) + bytes([ln]) + bytes(15) for n, t, ln in fields)
        row = b" " + "Lac Ha! Ha!".encode().ljust(12) + b"Permanent Water".ljust(16)
        rows = read_dbf(head + desc + b"\r" + row)
        self.assertEqual(rows, [{"NAME": "Lac Ha! Ha!", "TYPE": "Permanent Water"}])


class LambertTest(unittest.TestCase):
    def test_origin_and_round_trip(self):
        lcc = LambertConformalConic()
        x, y = lcc.forward(-95.0, 49.0)
        self.assertAlmostEqual(x, 0.0, places=6)
        self.assertAlmostEqual(y, 0.0, places=6)
        for lon, lat in [(-73.57, 45.50), (-60.0, 62.0), (-79.5, 44.5), (-57.1, 51.4)]:
            lo, la = lcc.inverse(*lcc.forward(lon, lat))
            self.assertAlmostEqual(lo, lon, places=7)
            self.assertAlmostEqual(la, lat, places=7)

    def test_scale_is_true_on_standard_parallel(self):
        # Sur le parallèle standard de 49°, 1° de longitude mesure a·cos(φ)/√(1−e²sin²φ) (ellipsoïde GRS 1980).
        import math
        lcc = LambertConformalConic()
        x0, y0 = lcc.forward(-95.0, 49.0)
        x1, y1 = lcc.forward(-94.999, 49.0)
        e2 = lcc.e ** 2
        phi = math.radians(49.0)
        expected = 6378137.0 * math.cos(phi) / math.sqrt(1 - e2 * math.sin(phi) ** 2) * math.radians(0.001)
        self.assertAlmostEqual(math.hypot(x1 - x0, y1 - y0), expected, delta=expected * 1e-6)


class ChannelTest(unittest.TestCase):
    def test_channel_prefers_water_and_avoids_blocked_hexes(self):
        g = HexGrid(radius=1.0, cols=6, rows=3)
        water = {g.index(0, 1), g.index(1, 1), g.index(4, 1)}
        sea = {g.index(5, 1)}
        cost = lambda c: 0.01 if c in water else 1.0
        path = channel(g, g.index(0, 1), sea, cost, set())
        self.assertEqual(path[0], g.index(0, 1))
        self.assertIn(path[-1], sea)
        self.assertIn(g.index(4, 1), path)  # passe par l'eau
        blocked = {g.index(2, 1), g.index(3, 1)}
        path2 = channel(g, g.index(0, 1), sea, cost, blocked)
        self.assertTrue(path2 and not set(path2) & blocked)
        wall = {g.index(2, r) for r in range(3)}
        self.assertIsNone(channel(g, g.index(0, 1), sea, cost, wall))

    def test_components(self):
        g = HexGrid(radius=1.0, cols=10, rows=1)
        self.assertEqual(sorted(map(sorted, components(g, {0, 1, 2, 5, 6, 9}))), [[0, 1, 2], [5, 6], [9]])


if __name__ == "__main__":
    unittest.main()
