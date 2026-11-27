"""Small, dependency-free geometry helpers.

Everything on the map lives in "map units": a spherical Lambert azimuthal equal-area projection centred on Québec
(core/quebec.py LON0, LAT0), multiplied by SCALE and shifted so the top-left of the map is (0, 0) and y points *down*
(like screen coordinates). Both the hex grid and the browser use this space. The art and the camera were tuned (in
usaciv) for 25-unit hexes, so one map unit is 1 / SCALE real kilometres (world.json `km_per_unit`): with SCALE = 5,
hexes are 5 km in radius, about 8.7 km across.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

R_EARTH_KM = 6371.0088


from .quebec import LAT0, LON0, SCALE  # noqa: E402  (map units per real km)


class Laea:
    """Lambert azimuthal equal-area on the sphere (radius R_EARTH_KM). Output in km, y up. Defaults: centred on Québec."""

    def __init__(self, lon0=LON0, lat0=LAT0):
        self.lon0, self.lat0 = math.radians(lon0), math.radians(lat0)
        self.sin0, self.cos0 = math.sin(self.lat0), math.cos(self.lat0)

    def __call__(self, lon: float, lat: float) -> tuple[float, float]:
        lam, phi = math.radians(lon) - self.lon0, math.radians(lat)
        sp, cp, cl = math.sin(phi), math.cos(phi), math.cos(lam)
        k = math.sqrt(2 / max(1e-12, 1 + self.sin0 * sp + self.cos0 * cp * cl))
        return R_EARTH_KM * k * cp * math.sin(lam), R_EARTH_KM * k * (self.cos0 * sp - self.sin0 * cp * cl)

    def inverse(self, x: float, y: float) -> tuple[float, float]:
        """km → (lon, lat)."""
        rho = math.hypot(x, y)
        if rho < 1e-9:
            return math.degrees(self.lon0), math.degrees(self.lat0)
        c = 2 * math.asin(min(1.0, rho / (2 * R_EARTH_KM)))
        sc, cc = math.sin(c), math.cos(c)
        lat = math.asin(max(-1.0, min(1.0, cc * self.sin0 + y * sc * self.cos0 / rho)))
        lon = self.lon0 + math.atan2(x * sc, rho * self.cos0 * cc - y * self.sin0 * sc)
        return math.degrees(lon), math.degrees(lat)



@dataclass
class MapProjection:
    """lon/lat → map units (origin top-left, y down). min_x/max_y are LAEA km of the map's top-left corner (before
    the margin); margin is in map units. Québec has no inset (`insets` is kept, always empty, for the browser)."""

    min_x: float
    max_y: float
    margin: float
    scale: float = SCALE
    insets: list | None = None

    def __post_init__(self):
        self._laea = Laea()

    def __call__(self, lon: float, lat: float) -> tuple[float, float]:
        x, y = self._laea(lon, lat)
        return (x - self.min_x) * self.scale + self.margin, (self.max_y - y) * self.scale + self.margin

    def km(self, lon: float, lat: float) -> tuple[float, float]:
        return self._laea(lon, lat)

    def inverse(self, x: float, y: float) -> tuple[float, float]:
        """map units → (lon, lat)."""
        return self._laea.inverse((x - self.margin) / self.scale + self.min_x, self.max_y - (y - self.margin) / self.scale)

    def to_dict(self) -> dict:
        return {"min_x": self.min_x, "max_y": self.max_y, "margin": self.margin, "scale": self.scale, "insets": []}


def ring_contains(ring: list[tuple[float, float]], x: float, y: float) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


class Shape:
    """A (multi)polygon as a bag of rings; even-odd rule handles holes."""

    def __init__(self, rings: Iterable[list[tuple[float, float]]]):
        self.rings = [r for r in rings if len(r) >= 3]
        xs = [p[0] for r in self.rings for p in r] or [0]
        ys = [p[1] for r in self.rings for p in r] or [0]
        self.bbox = (min(xs), min(ys), max(xs), max(ys))

    def contains(self, x: float, y: float) -> bool:
        x0, y0, x1, y1 = self.bbox
        if x < x0 or x > x1 or y < y0 or y > y1:
            return False
        inside = False
        for r in self.rings:
            if ring_contains(r, x, y):
                inside = not inside
        return inside


class ShapeIndex:
    """Bucket shapes by coarse grid square so point lookups only test a few shapes."""

    def __init__(self, shapes: list[Shape], cell_km: float = 100.0):
        self.shapes = shapes
        self.cell = cell_km
        self.buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
        for k, s in enumerate(shapes):
            x0, y0, x1, y1 = s.bbox
            for gx in range(int(x0 // cell_km), int(x1 // cell_km) + 1):
                for gy in range(int(y0 // cell_km), int(y1 // cell_km) + 1):
                    self.buckets[(gx, gy)].append(k)

    def locate(self, x: float, y: float) -> int:
        for k in self.buckets.get((int(x // self.cell), int(y // self.cell)), ()):
            if self.shapes[k].contains(x, y):
                return k
        return -1


# --- file formats -----------------------------------------------------------


def geojson_polygons(geom: dict) -> list[list[list[tuple[float, float]]]]:
    """A (Multi)Polygon as a list of polygons, each a list of rings (outer ring first, then holes)."""
    t, c = geom["type"], geom["coordinates"]
    polys = [c] if t == "Polygon" else c if t == "MultiPolygon" else []
    return [[[(x, y) for x, y, *_ in ring] for ring in poly] for poly in polys]


def geojson_rings(geom: dict) -> list[list[tuple[float, float]]]:
    t, c = geom["type"], geom["coordinates"]
    polys = [c] if t == "Polygon" else c if t == "MultiPolygon" else []
    return [[(round(x, 5), round(y, 5)) for x, y, *_ in ring] for poly in polys for ring in poly]


def geojson_lines(geom: dict) -> list[list[tuple[float, float]]]:
    t, c = geom["type"], geom["coordinates"]
    lines = [c] if t == "LineString" else c if t == "MultiLineString" else []
    return [[(round(x, 5), round(y, 5)) for x, y, *_ in line] for line in lines]


def load_geojson(path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["features"]


def bbox_intersects(points: Iterable[tuple[float, float]], bbox: tuple[float, float, float, float]) -> bool:
    x0, y0, x1, y1 = bbox
    return any(x0 <= x <= x1 and y0 <= y <= y1 for x, y in points)
