"""Répartition de la population (pipeline/build/places.py) : cas limites, sur une petite grille fictive."""

from __future__ import annotations

import unittest
from unittest import mock

from pipeline.build import places
from pipeline.core.hexgrid import HexGrid


class TinySdrTest(unittest.TestCase):
    """Une SDR trop petite pour un point d'échantillonnage va à l'hexagone de son centre, ou au plus proche du Québec."""

    def build(self, owner):
        grid = HexGrid(radius=25.0, cols=3, rows=3)
        world = {"grid": grid.to_dict(), "owner": owner, "csd": ["2400001"], "csd_cells": {},
                 "csd_point": {"0": list(grid.center(1, 1))}, "csd_type": ["MÉ"], "csd_state": [0]}
        pop = {"csd": {"2400001": {"name": "Îlot", "pop2021": 12, "pop2016": 10, "land_km2": 0.1}},
               "province": {"pop2021": 12}}
        saved = {}
        with mock.patch.object(places, "load_interim", side_effect={"_world": world, "statcan_population": pop}.get), \
                mock.patch.object(places, "save_interim", side_effect=lambda name, data: saved.update(data)), \
                mock.patch("builtins.print"):
            places.build()
        return grid, saved

    def test_population_goes_to_the_nearest_quebec_hex(self):
        owner = [-1] * 9
        owner[0] = 0  # le seul hexagone du Québec : un coin de la grille
        grid, saved = self.build(owner)
        self.assertEqual(saved["hexpop"][0], 12)
        self.assertEqual(sum(saved["hexpop"]), 12)

    def test_no_quebec_hex_nearby_is_an_error_not_the_last_hex(self):
        # Avant : nearest_owned renvoyait -1 et hexpop[-1] recevait la population, sans erreur.
        with self.assertRaises(ValueError):
            self.build([-2] * 9)


if __name__ == "__main__":
    unittest.main()
