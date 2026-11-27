"""Teinte de mélange du terrain (web/js/world.js landRGB) : proportionnelle à la part de forêt de l'hexagone, testée
avec Node s'il est installé."""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCRIPT = """
import { landRGB } from "%s";
const crop = [209, 176, 97], forest = [69, 112, 58];
const shares = [0, 1, 10, 50, 100];
const w = { raw: { elev: shares.map(() => 100) }, cover: shares.map(() => 7), relief: shares.map(() => 0),
  coverRGB: Object.assign([], { 3: forest, 7: crop }), pct: { forest: shares } };
const plain = { ...w, pct: null };
console.log(JSON.stringify({ tinted: shares.map((_, i) => landRGB(w, i)), plain: landRGB(plain, 0) }));
"""


@unittest.skipUnless(shutil.which("node"), "Node absent")
class TintTest(unittest.TestCase):
    def test_forest_tint_follows_the_forest_share(self):
        src = SCRIPT % (ROOT / "web/js/world.js").as_uri()
        out = subprocess.run(["node", "--input-type=module", "-e", src], capture_output=True, text=True, check=True)
        r = json.loads(out.stdout)
        none, one, ten, half, full = r["tinted"]

        def dist(a, b):
            return max(abs(x - y) for x, y in zip(a, b))

        self.assertEqual(none, r["plain"])  # 0 % de forêt : la couleur de la classe, sans teinte
        self.assertLess(dist(one, none), 1.0)  # 1 % de forêt : presque rien (avant : la teinte entière)
        self.assertLess(dist(ten, none), dist(half, none))
        self.assertLess(dist(half, none), dist(full, none))
        # 100 % de forêt : 30 % de la couleur de la forêt, comme dans le moteur d'origine.
        self.assertGreater(dist(full, none), 25)
        self.assertAlmostEqual(dist(half, none) / dist(full, none), 0.5, delta=0.02)


if __name__ == "__main__":
    unittest.main()
