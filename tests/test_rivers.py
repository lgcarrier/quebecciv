"""Rivières dessinées à leur largeur réelle (pipeline/core/rivers.py), sur de petits rasters faits à la main."""

from __future__ import annotations

import statistics
import unittest

from pipeline.core import rivers


def raster(rows):
    """is_water(c, r) and (columns, rows) of a raster drawn with « ~ » for water and « # » for land."""
    def is_water(c, r):
        return 0 <= r < len(rows) and 0 <= c < len(rows[r]) and rows[r][c] == "~"
    return is_water, (len(rows[0]), len(rows))


STRAIGHT = [  # un chenal de 3 pixels de large, puis la mer à droite
    "####################~~~~",
    "####################~~~~",
    "~~~~~~~~~~~~~~~~~~~~~~~~",
    "~~~~~~~~~~~~~~~~~~~~~~~~",
    "~~~~~~~~~~~~~~~~~~~~~~~~",
    "####################~~~~",
    "####################~~~~",
]


class RouteTest(unittest.TestCase):
    def test_follows_the_middle_of_the_water(self):
        is_water, size = raster(STRAIGHT)
        path = rivers.route(is_water, (0, 2), lambda c, r: c >= 21, size)  # part d'une rive
        self.assertEqual(path[0], (0, 2))
        self.assertGreaterEqual(path[-1][0], 21)
        self.assertTrue(all(r == 3 for c, r in path if 3 <= c <= 18), path)  # au milieu, loin des bouts

    def test_crosses_a_short_gap_of_land_but_prefers_water(self):
        rows = ["##########", "~~~~#~~~~~", "##########"]  # un barrage d'un pixel
        is_water, size = raster(rows)
        path = rivers.route(is_water, (0, 1), lambda c, r: c == 9, size)
        self.assertEqual(path, [(c, 1) for c in range(10)])
        rows = ["~~~~~~~~~~", "~########~", "~~~~#~~~~~"]  # le même barrage, avec un détour par l'eau
        is_water, size = raster(rows)
        path = rivers.route(is_water, (0, 2), lambda c, r: (c, r) == (9, 2), size)
        self.assertTrue(all(is_water(c, r) for c, r in path), path)

    def test_no_route_outside_the_raster(self):
        is_water, size = raster(["~~~###", "~~~###"])
        self.assertIsNone(rivers.route(is_water, (0, 0), lambda c, r: c > 99, size))

    def test_nearest_water(self):
        is_water, _ = raster(STRAIGHT)
        self.assertEqual(rivers.nearest_water(is_water, 5, 3), (5, 3))
        self.assertEqual(rivers.nearest_water(is_water, 5, 0), (5, 2))
        self.assertIsNone(rivers.nearest_water(lambda c, r: False, 5, 0, radius=3))


class WidthTest(unittest.TestCase):
    def test_width_and_centre_of_a_straight_channel(self):
        is_water, _ = raster(STRAIGHT)
        path = [(c, 2) for c in range(4, 16)]  # le long de la rive du haut, pas au milieu
        sections = rivers.cross_sections(is_water, path)
        for c, r, w in sections:
            self.assertAlmostEqual(w, 3.0, delta=0.3)  # 3 pixels d'eau en travers
            self.assertAlmostEqual(r, 3.0, delta=0.15)  # ramené au milieu du chenal
        self.assertEqual([round(c) for c, _, _ in sections], [c for c, _ in path])

    def test_land_has_no_width(self):
        is_water, _ = raster(["####", "####"])
        self.assertEqual(rivers.cross_sections(is_water, [(0, 0), (1, 0), (2, 0)]), [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)])

    def test_running(self):
        self.assertEqual(rivers.running([1, 1, 9, 1, 1], 1, statistics.median), [1, 1, 1, 1, 1])


class ShapeTest(unittest.TestCase):
    def test_land_runs_keep_an_overlap_into_the_water(self):
        land = [False] * 10 + [True] * 8 + [False] * 10
        self.assertEqual(rivers.land_runs(land, overlap=4), [(6, 22)])
        self.assertEqual(rivers.land_runs([True] * 5, overlap=4), [(0, 5)])  # sans dépasser les bouts

    def test_land_runs_drop_a_clipped_corner_and_merge_neighbours(self):
        self.assertEqual(rivers.land_runs([False] * 6 + [True] * 2 + [False] * 6, overlap=2), [])
        land = [True] * 5 + [False] * 3 + [True] * 5
        self.assertEqual(rivers.land_runs(land, overlap=2), [(0, 13)])

    def test_land_runs_end_over_water(self):
        # Un bout de terre trop court pour un tronçon, juste après la fin : le tronçon le traverse et finit dans l'eau.
        land = [False] * 4 + [True] * 6 + [False] * 2 + [True] + [False] * 8
        (a, b), = rivers.land_runs(land, overlap=3)
        self.assertEqual((a, b), (1, 16))
        self.assertFalse(land[a] or land[b - 1])

    def test_simplify_keeps_the_bends(self):
        pts = [(0, 0), (1, 0.01), (2, 0), (3, 0), (3, 1), (3, 2)]
        self.assertEqual(rivers.simplify(pts, 0.1), [0, 3, 5])
        self.assertEqual(rivers.simplify(pts[:2], 0.1), [0, 1])

    def test_smooth_keeps_the_ends_and_carries_the_widths(self):
        pts, ws = rivers.smooth([(0, 0), (4, 0), (4, 4)], [1.0, 2.0, 3.0])
        self.assertEqual((pts[0], pts[-1]), ((0, 0), (4, 4)))
        self.assertEqual(len(pts), len(ws))
        self.assertEqual((ws[0], ws[-1]), (1.0, 3.0))
        self.assertNotIn((4, 0), pts)  # le coin est coupé
        self.assertTrue(all(1.0 <= w <= 3.0 for w in ws))


if __name__ == "__main__":
    unittest.main()
