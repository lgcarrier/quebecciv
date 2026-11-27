"""Fichiers des limites cartographiques du Recensement de 2021 (Statistique Canada), lus par le service ArcGIS REST
public de Statistique Canada (geo.statcan.gc.ca) : subdivisions de recensement (SDR, les municipalités, réserves et
territoires non organisés) du Québec, divisions de recensement (DR : MRC et territoires équivalents), régions
économiques (= régions administratives du Québec) et provinces voisines.

Les fichiers « cartographiques » sont découpés au trait de côte : ce qui n'est couvert par aucune SDR est de l'eau
(ou hors du Québec). Les géométries sont simplifiées par le serveur (maxAllowableOffset) et arrondies à 5 décimales :
c'est largement assez fin pour des hexagones de 5 km de rayon."""

from __future__ import annotations

import json
import urllib.parse

from ..core.geo import geojson_polygons
from ..core.quebec import BBOX, NEIGHBOUR_PROVINCES, PRUID
from ..core.source import Source, SourceInfo

SERVICE = "https://geo.statcan.gc.ca/geo_wa/rest/services/2021/Cartographic_boundary_files/MapServer"
LAYER = {"PR": 0, "ER": 2, "CD": 4, "CMA": 6, "CSD": 9}
PAGE = 200  # entités par requête (le service en permet 6 000, mais les réponses restent ainsi de taille raisonnable)
CSD_COUNT = 1282  # SDR du Québec en 2021 ; process() vérifie le compte


def _query(layer: str, where: str, fields: str, *, geometry: bool, offset_deg: float = 0.002, page: int | None = None,
           envelope: tuple | None = None) -> str:
    q = {"where": where, "outFields": fields, "returnGeometry": "true" if geometry else "false", "f": "geojson",
         "orderByFields": "OBJECTID"}
    if geometry:
        q |= {"outSR": "4326", "maxAllowableOffset": str(offset_deg), "geometryPrecision": "5"}
    if page is not None:
        q |= {"resultOffset": str(page * PAGE), "resultRecordCount": str(PAGE)}
    if envelope:
        q |= {"geometry": ",".join(str(v) for v in envelope), "geometryType": "esriGeometryEnvelope", "inSR": "4326",
              "spatialRel": "esriSpatialRelIntersects"}
    return f"{SERVICE}/{LAYER[layer]}/query?{urllib.parse.urlencode(q)}"


class StatcanBoundaries(Source):
    info = SourceInfo(
        id="statcan_boundaries",
        title="Fichiers des limites cartographiques, Recensement de 2021",
        publisher="Statistique Canada",
        homepage="https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/index2021-fra.cfm",
        license="Licence du gouvernement ouvert – Canada",
        description="Limites des 1 282 subdivisions de recensement du Québec (municipalités, réserves, terres "
        "réservées, villages nordiques, territoires non organisés), des divisions de recensement (MRC et "
        "équivalents), des 17 régions économiques (les régions administratives du Québec) et des provinces "
        "voisines, lues par le service ArcGIS REST de Statistique Canada (géométries simplifiées à environ 200 m "
        "par le serveur). Les limites cartographiques suivent le trait de côte : elles décident ce qui est terre "
        "ou eau sur la carte.",
        used_for=["Terre et eau", "Régions administratives", "MRC (divisions de recensement)",
                  "Position des municipalités", "Répartition de la population sur les hexagones"],
    )

    def _files(self):
        files = [(f"csd_{k}.geojson", _query("CSD", f"PRUID='{PRUID}'", "CSDUID,CSDNAME,CSDTYPE,LANDAREA",
                                               geometry=True, page=k))
                 for k in range((CSD_COUNT + PAGE - 1) // PAGE)]
        files.append(("er.geojson", _query("ER", f"PRUID='{PRUID}'", "ERUID,ERNAME,LANDAREA", geometry=True,
                                           offset_deg=0.005)))
        files.append(("cd.geojson", _query("CD", f"PRUID='{PRUID}'", "CDUID,CDNAME,CDTYPE,LANDAREA",
                                           geometry=False)))
        provs = ",".join(f"'{p}'" for p in NEIGHBOUR_PROVINCES)
        files.append(("neighbours.geojson", _query("PR", f"PRUID IN ({provs})", "PRUID,PRFNAME,PRENAME",
                                                   geometry=True, offset_deg=0.01, envelope=BBOX)))
        return files

    def fetch(self, force=False):
        for rel, url in self._files():
            self.download(url, rel, force=force)

    def _features(self, rel):
        with open(self.raw_dir / rel, encoding="utf-8") as f:
            d = json.load(f)
        if "features" not in d:
            raise ValueError(f"{rel}: pas une réponse GeoJSON ({str(d)[:200]})")
        return d["features"]

    def process(self):
        files = [rel for rel, _ in self._files()]
        csd = []
        for rel in files:
            if not rel.startswith("csd_"):
                continue
            for f in self._features(rel):
                p = f["properties"]
                csd.append({"uid": p["CSDUID"], "name": p["CSDNAME"], "type": p["CSDTYPE"],
                            "land_km2": p["LANDAREA"], "polys": geojson_polygons(f["geometry"])})
        uids = [c["uid"] for c in csd]
        if len(set(uids)) != len(uids) or len(uids) != CSD_COUNT:
            raise ValueError(f"{len(uids)} SDR ({len(set(uids))} distinctes) au lieu de {CSD_COUNT}")
        csd.sort(key=lambda c: c["uid"])
        er = [{"uid": f["properties"]["ERUID"], "name": f["properties"]["ERNAME"],
               "land_km2": f["properties"]["LANDAREA"], "polys": geojson_polygons(f["geometry"])}
              for f in self._features("er.geojson")]
        cd = [{"uid": f["properties"]["CDUID"], "name": f["properties"]["CDNAME"], "type": f["properties"]["CDTYPE"],
               "land_km2": f["properties"]["LANDAREA"]} for f in self._features("cd.geojson")]
        neighbours = [{"uid": f["properties"]["PRUID"], "name": f["properties"]["PRFNAME"],
                       "polys": geojson_polygons(f["geometry"])} for f in self._features("neighbours.geojson")]
        return {
            "vintage": "Recensement de 2021, limites cartographiques (géographie au 1er janvier 2021)",
            "_files": files,
            "csd": csd,
            "er": sorted(er, key=lambda e: e["uid"]),
            "cd": sorted(cd, key=lambda c: c["uid"]),
            "neighbours": neighbours,
        }
