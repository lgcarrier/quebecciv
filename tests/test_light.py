"""`pipeline --light` : les sources facultatives (la couverture du sol, 2,1 Go) sont laissées de côté."""

from __future__ import annotations

import contextlib
import io
import unittest

from pipeline import __main__ as cli
from pipeline.build import world
from pipeline.core import landcover
from pipeline.sources import BY_ID


class LightTest(unittest.TestCase):
    def pick(self, names, light, keep=lambda sid: False):
        with contextlib.redirect_stdout(io.StringIO()):
            return cli._without_optional(list(names or BY_ID), names, light, keep)

    def test_only_the_land_cover_is_optional(self):
        self.assertEqual([sid for sid, s in BY_ID.items() if s.optional], ["nrcan_landcover"])

    def test_light_leaves_optional_sources_out(self):
        self.assertNotIn("nrcan_landcover", self.pick([], True))
        self.assertEqual(len(self.pick([], True)), len(BY_ID) - 1)

    def test_without_light_or_when_named_nothing_is_left_out(self):
        self.assertIn("nrcan_landcover", self.pick([], False))
        self.assertEqual(self.pick(["nrcan_landcover"], True), ["nrcan_landcover"])

    def test_process_keeps_an_optional_source_already_downloaded(self):
        self.assertIn("nrcan_landcover", self.pick([], True, keep=lambda sid: True))

    def test_the_world_builder_does_not_require_the_land_cover(self):
        self.assertNotIn("nrcan_landcover", world.REQUIRES)
        self.assertIn("nrcan_landcover", world.OPTIONAL)
        self.assertEqual([t["id"] for t in landcover.NO_COVER_TABLE], [0])


if __name__ == "__main__":
    unittest.main()
