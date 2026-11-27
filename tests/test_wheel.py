"""Zoom à la molette : facteur borné et proportionnel (web/js/camera.js), testé avec Node s'il est installé."""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCRIPT = """
import { wheelZoomFactor as f } from "%s";
const ev = (deltaY, deltaMode = 0, ctrlKey = false) => ({ deltaY, deltaMode, ctrlKey });
let chrome = 1, firefox = 1, pad = 1, pinch = 1;
for (let i = 0; i < 10; i++) { chrome *= f(ev(-100), 800); firefox *= f(ev(-3, 1), 800); }
for (let i = 0; i < 40; i++) pad *= f(ev(-4), 800);
for (let i = 0; i < 20; i++) pinch *= f(ev(-5, 0, true), 800);
console.log(JSON.stringify({ chrome, firefox, pad, pinch, huge: f(ev(-5000), 800), page: f(ev(-1, 2), 800),
  zero: f(ev(0), 800), out: f(ev(100), 800) }));
"""


@unittest.skipUnless(shutil.which("node"), "Node absent")
class WheelTest(unittest.TestCase):
    def test_wheel_zoom_is_gentle_and_capped(self):
        src = SCRIPT % (ROOT / "web/js/camera.js").as_uri()
        out = subprocess.run(["node", "--input-type=module", "-e", src], capture_output=True, text=True, check=True)
        r = json.loads(out.stdout)
        self.assertTrue(3.0 < r["chrome"] < 5.0, r)  # 10 crans de souris : environ ×4
        self.assertAlmostEqual(r["chrome"], r["firefox"], delta=0.2)  # lignes (Firefox) ≈ pixels (Chrome)
        self.assertAlmostEqual(r["huge"], r["page"])  # un événement énorme est plafonné comme un cran
        self.assertLess(r["huge"], 1.2)
        self.assertTrue(1.1 < r["pad"] < 1.5, r)  # pavé tactile : 160 px ≈ ×1,25
        self.assertTrue(2.0 < r["pinch"] < 3.5, r)  # pincement (ctrlKey) reste vif
        self.assertEqual(r["zero"], 1)
        self.assertLess(r["out"], 1)


if __name__ == "__main__":
    unittest.main()
