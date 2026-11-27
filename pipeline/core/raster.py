"""A tiny label raster in projected km, filled polygon by polygon with an even-odd scanline (standard library only).

The world builder rasterises the census subdivisions (and neighbours, lakes, regions) at RASTER_KM resolution, then
reads the raster at a lattice of sample points inside each hex. Values are small integers (array 'h')."""

from __future__ import annotations

import math
from array import array


class Raster:
    def __init__(self, x0: float, y0: float, px_km: float, width: int, height: int, fill: int = -1, typecode="h"):
        """x0, y0: km of the top-left corner (y up in km, rows go down)."""
        self.x0, self.y0, self.px = x0, y0, px_km
        self.w, self.h = width, height
        self.data = array(typecode, [fill]) * (width * height)

    def rc(self, x: float, y: float) -> tuple[int, int]:
        return int((x - self.x0) // self.px), int((self.y0 - y) // self.px)

    def get(self, x: float, y: float, default: int = -1) -> int:
        c, r = int((x - self.x0) // self.px), int((self.y0 - y) // self.px)
        if 0 <= c < self.w and 0 <= r < self.h:
            return self.data[r * self.w + c]
        return default

    def fill_polygon(self, rings_km: list[list[tuple[float, float]]], value: int, only_over: int | None = None) -> int:
        """Fill one polygon (outer ring + holes, even-odd) with `value` at pixel centres. With `only_over`, only
        pixels that hold that value are written. Returns the number of pixels written."""
        px, x0, y0, w = self.px, self.x0, self.y0, self.w
        rows: dict[int, list[float]] = {}
        for ring in rings_km:
            n = len(ring)
            if n < 3:
                continue
            for k in range(n):
                ax, ay = ring[k - 1]
                bx, by = ring[k]
                if ay == by:
                    continue
                # pixel-centre rows j with y_j = y0 - (j + 0.5) * px strictly between the edge's ends (half-open)
                ra, rb = (y0 - ay) / px - 0.5, (y0 - by) / px - 0.5
                lo, hi = (ra, rb) if ra < rb else (rb, ra)
                j0, j1 = max(0, math.ceil(lo)), min(self.h - 1, math.ceil(hi) - 1)
                if j0 > j1:
                    continue
                inv = (bx - ax) / (rb - ra)
                for j in range(j0, j1 + 1):
                    rows.setdefault(j, []).append(ax + (j - ra) * inv)
        written = 0
        data = self.data
        for j, xs in rows.items():
            xs.sort()
            base = j * w
            for k in range(0, len(xs) - 1, 2):
                c0 = max(0, math.ceil((xs[k] - x0) / px - 0.5))
                c1 = min(w - 1, math.ceil((xs[k + 1] - x0) / px - 0.5) - 1)
                if c0 > c1:
                    continue
                if only_over is None:
                    data[base + c0: base + c1 + 1] = array(data.typecode, [value]) * (c1 - c0 + 1)
                    written += c1 - c0 + 1
                else:
                    for c in range(c0, c1 + 1):
                        if data[base + c] == only_over:
                            data[base + c] = value
                            written += 1
        return written
