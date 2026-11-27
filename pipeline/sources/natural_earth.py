"""Natural Earth 1:10m : lacs (avec le complément nord-américain), rivières et les États-Unis voisins."""

from __future__ import annotations

from ..core.geo import bbox_intersects, geojson_lines, geojson_polygons, load_geojson
from ..core.quebec import BBOX
from ..core.source import Source, SourceInfo

# Épinglé sur une version : le contenu (et son sha256) ne peut pas changer sous la même URL.
TAG = "v5.1.2"
BASE = f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{TAG}/geojson"


def _r5(polys):
    return [[[(round(x, 5), round(y, 5)) for x, y in ring] for ring in poly] for poly in polys]


class NaturalEarth(Source):
    info = SourceInfo(
        id="natural_earth",
        title="Natural Earth 1:10m (lacs, rivières, États-Unis)",
        publisher="Natural Earth",
        homepage="https://www.naturalearthdata.com/",
        license="Domaine public",
        description="Contours des lacs (avec le complément nord-américain) pour distinguer les lacs de la mer, tracé "
        f"des rivières et contour des États-Unis autour du Québec. Fichiers épinglés sur natural-earth-vector {TAG}.",
        used_for=["Lacs", "Rivières", "États-Unis (voisin)"],
    )

    FILES = ["ne_10m_admin_0_countries", "ne_10m_lakes", "ne_10m_lakes_north_america",
             "ne_10m_rivers_lake_centerlines", "ne_10m_rivers_north_america"]

    def _path(self, name):
        return f"{TAG}/{name}.geojson"

    def fetch(self, force=False):
        for name in self.FILES:
            self.download(f"{BASE}/{name}.geojson", self._path(name), force=force)

    def _features(self, name):
        return load_geojson(self.raw_dir / self._path(name))

    def process(self):
        countries = []
        for f in self._features("ne_10m_admin_0_countries"):
            if f["properties"].get("ADM0_A3") == "USA":
                polys = [p for p in geojson_polygons(f["geometry"] or {"type": None, "coordinates": None}) if bbox_intersects(p[0], BBOX)]
                countries.append({"name": "États-Unis", "polys": _r5(polys)})
        lakes = []
        for name in ("ne_10m_lakes", "ne_10m_lakes_north_america"):
            for f in self._features(name):
                polys = [p for p in geojson_polygons(f["geometry"] or {"type": None, "coordinates": None}) if bbox_intersects(p[0], BBOX)]
                if polys:
                    lakes.append({"name": f["properties"].get("name"), "polys": _r5(polys)})
        rivers = []
        for name in ("ne_10m_rivers_lake_centerlines", "ne_10m_rivers_north_america"):
            for f in self._features(name):
                p = f["properties"]
                lines = [ln for ln in geojson_lines(f["geometry"]) if bbox_intersects(ln, BBOX)] if f["geometry"] else []
                if lines and p.get("featurecla", "").startswith("River"):
                    rivers.append({"name": p.get("name_fr") or p.get("name"), "rank": p.get("scalerank"), "lines": lines})
        return {"vintage": f"Natural Earth 1:10m ({TAG})", "_files": [self._path(n) for n in self.FILES],
                "countries": countries, "lakes": lakes, "rivers": rivers}
