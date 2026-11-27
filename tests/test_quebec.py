"""Tests propres au Québec : projection, grille d'hexagones, matricielle et totaux de population.

Les tests de données lisent web/data (versionné) : ils échouent si le pipeline n'a pas été rebâti après un changement.
"""

import json
import math
import unittest
from pathlib import Path

from pipeline.core.geo import Laea, R_EARTH_KM
from pipeline.core.hexgrid import HexGrid
from pipeline.core.quebec import HEX_RADIUS_UNITS, LAT0, LON0, SCALE
from pipeline.core.raster import Raster

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "data"
# Population du Québec au Recensement de 2021, tableau 98-10-0002-01 de Statistique Canada (ligne de la province).
OFFICIAL_QC_2021 = 8_501_833


def load(name):
    return json.loads((WEB / name).read_text(encoding="utf-8"))


class ProjectionTest(unittest.TestCase):
    def test_centre_is_origin(self):
        x, y = Laea()(LON0, LAT0)
        self.assertAlmostEqual(x, 0, places=6)
        self.assertAlmostEqual(y, 0, places=6)

    def test_roundtrip_over_quebec(self):
        p = Laea()
        for lon in (-79.5, -73.57, -71.21, -68.5, -64.0, -57.1):
            for lat in (45.0, 46.8, 50.2, 55.3, 58.1, 62.4):
                x, y = p(lon, lat)
                lon2, lat2 = p.inverse(x, y)
                self.assertAlmostEqual(lon, lon2, places=7)
                self.assertAlmostEqual(lat, lat2, places=7)

    def test_equal_area(self):
        # Un quadrilatère de 0,1° × 0,1° garde l'aire sphérique exacte, au sud comme au nord du Québec.
        p = Laea()
        for lon, lat in ((-73.6, 45.5), (-68.5, 53.5), (-77.0, 62.0), (-58.0, 51.4)):
            d = 0.1
            pts = [p(lon, lat), p(lon + d, lat), p(lon + d, lat + d), p(lon, lat + d)]
            shoelace = 0.5 * abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1])))
            sphere = R_EARTH_KM ** 2 * math.radians(d) * (math.sin(math.radians(lat + d)) - math.sin(math.radians(lat)))
            self.assertAlmostEqual(shoelace / sphere, 1.0, delta=1e-4)

    def test_montreal_south_west_of_centre(self):
        x, y = Laea()(-73.57, 45.50)
        self.assertLess(x, 0)
        self.assertLess(y, 0)


class GridTest(unittest.TestCase):
    def test_hex_size_is_5_km(self):
        self.assertEqual(HEX_RADIUS_UNITS / SCALE, 5.0)
        w = load("world.json")
        self.assertAlmostEqual(w["grid"]["radius"] * w["km_per_unit"], 5.0)

    def test_grid_covers_the_map(self):
        w = load("world.json")
        g = w["grid"]
        self.assertEqual((g["cols"], g["rows"]), (202, 281))
        grid = HexGrid.covering(w["width"], w["height"], g["radius"])
        self.assertEqual((grid.cols, grid.rows), (g["cols"], g["rows"]))
        self.assertEqual(len(w["owner"]), g["cols"] * g["rows"])

    def test_quebec_hex_count(self):
        w = load("world.json")
        n = sum(1 for o in w["owner"] if o >= 0)
        self.assertEqual(n, 22_575)
        # ~65 km² par hexagone : l'aire de la terre québécoise (eaux intérieures exclues) reste de l'ordre de la
        # superficie du Québec.
        hex_km2 = 3 * math.sqrt(3) / 2 * 5.0 ** 2
        self.assertTrue(1.3e6 < n * hex_km2 < 1.6e6, n * hex_km2)

    def test_st_lawrence_is_continuous_water(self):
        # Le Saint-Laurent fluvial est une suite d'hexagones d'eau, du lac Saint-Louis (Montréal) à l'estuaire.
        w = load("world.json")
        proj = load("projection.json")
        from pipeline.core.geo import MapProjection
        mp = MapProjection(proj["min_x"], proj["max_y"], proj["margin"], proj["scale"])
        grid = HexGrid.covering(w["width"], w["height"], w["grid"]["radius"])
        start = grid.cell_at(*mp(-73.85, 45.40))  # lac Saint-Louis
        goal = grid.cell_at(*mp(-68.3, 48.9))  # estuaire (étiquette de la carte)
        lac_st_pierre = grid.cell_at(*mp(-72.85, 46.20))
        for c in (start, goal, lac_st_pierre):
            self.assertEqual(w["owner"][c], -1, c)
        seen, q = {start}, [start]
        for c in q:
            for n in grid.neighbours(c):
                if n not in seen and w["owner"][n] == -1:
                    seen.add(n)
                    q.append(n)
        self.assertIn(lac_st_pierre, seen)
        self.assertIn(goal, seen)
        chicoutimi = grid.cell_at(*mp(-71.06, 48.43))  # le Saguenay rejoint aussi l'estuaire
        self.assertIn(chicoutimi, seen)

    @unittest.skipUnless((ROOT / "data" / "interim" / "_places.json").exists(), "data/interim absent")
    def test_every_inhabited_municipality_has_land_of_its_own(self):
        # Chaque SDR habitée garde au moins un hexagone de terre où elle a des points (îles de Montréal, Laval,
        # Île Perrot, Île d'Orléans, Kirkland, Beaconsfield…), et sa population y reste.
        wi = json.loads((ROOT / "data" / "interim" / "_world.json").read_text())["data"]
        pl = json.loads((ROOT / "data" / "interim" / "_places.json").read_text())["data"]
        self.assertEqual(pl["without_own_hex"], [])
        pop = {r[0]: r[3] for r in pl["rows"]}
        owner = wi["owner"]
        for k, cells in wi["csd_cells"].items():
            uid = wi["csd"][int(k)]
            if pop.get(uid):
                self.assertTrue(any(owner[c[0]] >= 0 for c in cells), wi["csd_name"][int(k)])
        names = {wi["csd_name"][int(k)] for k in wi["csd_cells"]}
        for name in ("Kirkland", "Beaconsfield", "L'Île-Perrot", "Laval", "Saint-Pierre-de-l'Île-d'Orléans"):
            self.assertIn(name, names)

    def test_quebec_extremes_are_on_quebec_hexes(self):
        # Des lieux aux quatre coins du Québec tombent dans la carte et sur un hexagone québécois.
        w = load("world.json")
        proj = load("projection.json")
        from pipeline.core.geo import MapProjection
        mp = MapProjection(proj["min_x"], proj["max_y"], proj["margin"], proj["scale"])
        g = w["grid"]
        grid = HexGrid.covering(w["width"], w["height"], g["radius"])
        places = {
            "Ivujivik": (-77.91, 62.42), "Blanc-Sablon": (-57.13, 51.43), "Témiscaming": (-79.10, 46.72),
            "Montréal": (-73.57, 45.50), "Gaspé": (-64.48, 48.83), "Kuujjuaq": (-68.40, 58.10),
        }
        for name, (lon, lat) in places.items():
            x, y = mp(lon, lat)
            self.assertTrue(0 <= x <= w["width"] and 0 <= y <= w["height"], name)
            cell = grid.cell_at(x, y)
            self.assertGreaterEqual(cell, 0, name)
            near = [cell] + grid.neighbours(cell)
            self.assertTrue(any(w["owner"][k] >= 0 for k in near), name)


class RasterTest(unittest.TestCase):
    def test_square_with_hole(self):
        r = Raster(0.0, 10.0, 1.0, 10, 10)
        outer = [(1, 1), (9, 1), (9, 9), (1, 9)]
        hole = [(4, 4), (6, 4), (6, 6), (4, 6)]
        n = r.fill_polygon([outer, hole], 7)
        self.assertEqual(n, 64 - 4)
        self.assertEqual(r.get(2.5, 2.5), 7)
        self.assertEqual(r.get(5.0, 5.0), -1)  # dans le trou
        self.assertEqual(r.get(0.5, 0.5), -1)  # hors du carré

    def test_only_over(self):
        r = Raster(0.0, 4.0, 1.0, 4, 4)
        r.fill_polygon([[(0, 0), (2, 0), (2, 4), (0, 4)]], 1)
        n = r.fill_polygon([[(0, 0), (4, 0), (4, 4), (0, 4)]], 2, only_over=-1)
        self.assertEqual(n, 8)
        self.assertEqual(r.get(0.5, 0.5), 1)
        self.assertEqual(r.get(3.5, 0.5), 2)


class PopulationTest(unittest.TestCase):
    def test_nation_matches_official_total(self):
        n = load("nation.json")["nation"]
        self.assertEqual(n["population_official"], OFFICIAL_QC_2021)
        self.assertEqual(n["population"], OFFICIAL_QC_2021)

    def test_sum_of_csd_is_official_total(self):
        c = load("communes.json")
        col = {k: i for i, k in enumerate(c["columns"])}
        rows = c["rows"]
        self.assertEqual(len(rows), 1282)
        self.assertEqual(sum(r[col["pop"]] or 0 for r in rows), OFFICIAL_QC_2021)
        unpublished = [r[col["name"]] for r in rows if r[col["pop"]] is None]
        self.assertEqual(len(unpublished), 8)

    def test_sum_of_regions_is_official_total(self):
        st = load("states.json")
        states = st["states"] if isinstance(st, dict) else st
        self.assertEqual(len(states), 17)
        self.assertEqual(sum(s["population"] for s in states), OFFICIAL_QC_2021)

    def test_hex_density_is_finite_on_quebec(self):
        w = load("world.json")
        dens = load("lenses/density.json")
        values = dens["values"] if isinstance(dens, dict) else dens
        quebec = [i for i, o in enumerate(w["owner"]) if o >= 0]
        self.assertTrue(all(values[i] is not None and values[i] >= 0 for i in quebec))

    def test_capital_is_quebec_city(self):
        cities = load("cities.json")
        cities = cities["cities"] if isinstance(cities, dict) else cities
        caps = [c for c in cities if c.get("capital")]
        self.assertEqual([c["name"] for c in caps], ["Québec"])


class CheckTest(unittest.TestCase):
    def test_pipeline_check_has_no_failure(self):
        from pipeline import check
        r = check.run(quiet=True)
        self.assertEqual(r.count("FAIL"), 0)


if __name__ == "__main__":
    unittest.main()
