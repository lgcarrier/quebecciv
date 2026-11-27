"""Couverture du sol par hexagone, à partir des points de la couverture du sol du Canada 2020 (sources/nrcan_landcover).

Chaque point (un tous les 480 m) est rapporté à son hexagone ; la part d'une classe dans l'hexagone est sa part des
points (classe 0, hors des données, exclue). La classe dominante est la classe de terre (eau exclue) qui a le plus de
points ; elle donne la couleur de l'hexagone."""

from __future__ import annotations

import base64
import zlib

# Classe NALCMS (RNCan 2020) → (id de couverture de la carte, groupe). Les id 1 à 11 sont ceux du moteur
# (web/js/terrain.js COVER) ; 12 à 14 sont propres au Québec (taïga, toundra, arbustaie), sans dessin particulier.
NALCMS = {
    1: (2, "forest"),     # forêt de conifères sempervirente tempérée ou subpolaire
    2: (12, "forest"),    # forêt de conifères (taïga) subpolaire
    5: (1, "forest"),     # forêt feuillue
    6: (3, "forest"),     # forêt mixte
    8: (14, "shrub"),     # arbustaie tempérée ou subpolaire
    10: (5, "grass"),     # prairie tempérée ou subpolaire
    11: (13, "shrub"),    # arbustaie à lichens et à mousses (toundra arbustive)
    12: (13, "grass"),    # prairie à lichens et à mousses (toundra herbacée)
    13: (13, "barren"),   # lande à lichens et à mousses (toundra)
    14: (8, "wetland"),   # milieu humide
    15: (7, "crop"),      # terre cultivée
    16: (10, "barren"),   # lande (roc, sable)
    17: (9, "developed"),  # milieu urbain
    18: (0, "water"),     # eau
    19: (11, "ice"),      # neige et glace
}
GROUPS = ["forest", "shrub", "grass", "crop", "wetland", "developed", "barren", "ice", "water"]
FOREST_CLASSES = [k for k, (_, g) in NALCMS.items() if g == "forest"]

# Table de couverture de world.json (ids du moteur + 12 à 14). Couleurs : tons de carte de jeu proches de la légende
# officielle de RNCan (conifères sombres, feuillus plus clairs, taïga olive, toundra beige-vert…).
COVER_TABLE = [
    {"id": 0, "key": "none", "name": "Sans données", "rule": "Hors de la couverture du sol du Canada (États-Unis) : "
     "la couleur suit l'altitude."},
    {"id": 1, "key": "forest_deciduous", "name": "Forêt de feuillus", "color": "#4f8a3a",
     "rule": "Classe dominante : forêt feuillue tempérée ou subpolaire (NALCMS 5)."},
    {"id": 2, "key": "forest_evergreen", "name": "Forêt de conifères", "color": "#2c5435",
     "rule": "Classe dominante : forêt de conifères sempervirente tempérée ou subpolaire (NALCMS 1)."},
    {"id": 3, "key": "forest_mixed", "name": "Forêt mixte", "color": "#45703a",
     "rule": "Classe dominante : forêt mixte (NALCMS 6)."},
    {"id": 5, "key": "grassland", "name": "Prairie", "color": "#b9b56a",
     "rule": "Classe dominante : prairie tempérée ou subpolaire (NALCMS 10)."},
    {"id": 7, "key": "cropland", "name": "Terres cultivées", "color": "#d1b061",
     "rule": "Classe dominante : terre cultivée (NALCMS 15)."},
    {"id": 8, "key": "wetland", "name": "Milieu humide", "color": "#5f8f78",
     "rule": "Classe dominante : milieu humide (NALCMS 14)."},
    {"id": 9, "key": "urban", "name": "Bâti", "color": "#9a8f86",
     "rule": "Classe dominante : milieu urbain (NALCMS 17)."},
    {"id": 10, "key": "barren", "name": "Roc et sable", "color": "#a9a8a2",
     "rule": "Classe dominante : lande, roc ou sable (NALCMS 16)."},
    {"id": 11, "key": "ice", "name": "Neige et glace", "color": "#eef3f5",
     "rule": "Classe dominante : neige et glace (NALCMS 19)."},
    {"id": 12, "key": "taiga", "name": "Taïga", "color": "#6f7f52",
     "rule": "Classe dominante : forêt de conifères (taïga) subpolaire, clairsemée (NALCMS 2)."},
    {"id": 13, "key": "tundra", "name": "Toundra", "color": "#a3a47c",
     "rule": "Classe dominante : arbustaie, prairie ou lande à lichens et à mousses, polaire ou subpolaire (NALCMS 11 à 13)."},
    {"id": 14, "key": "shrubland", "name": "Arbustaie", "color": "#8f8a4e",
     "rule": "Classe dominante : arbustaie tempérée ou subpolaire (NALCMS 8), souvent une coupe ou un brûlis qui se "
     "reboise."},
]


class LandcoverPoints:
    """The interim points: a regular grid in the source projection, one class byte per point."""

    def __init__(self, lc: dict):
        self.x0, self.y0, self.dx, self.dy = lc["x0"], lc["y0"], lc["dx"], lc["dy"]
        self.w, self.h = lc["width"], lc["height"]
        self.data = zlib.decompress(base64.b64decode(lc["data_zlib_b64"]))
        if len(self.data) != self.w * self.h:
            raise ValueError("couverture du sol : taille des données inattendue")


def hex_counts(pts: LandcoverPoints, to_map, cell_at, block: int = 16) -> dict:
    """{cell: {class: points}}. `to_map(x, y)` → map units from the source projection; `cell_at(ux, uy)` → hex or −1.
    Positions inside a block of block × block points are interpolated from its corners (the error is a few metres
    for a 7.7 km block, nothing next to a 5 km hex)."""
    counts: dict[int, dict[int, int]] = {}
    data, w, h = pts.data, pts.w, pts.h
    for by in range(0, h, block):
        ry = min(block, h - by)
        for bx in range(0, w, block):
            rx = min(block, w - bx)
            rows = [data[(by + j) * w + bx:(by + j) * w + bx + rx] for j in range(ry)]
            if not any(any(r) for r in rows):
                continue
            corners = []
            for j in (0, ry):
                for i in (0, rx):
                    corners.append(to_map(pts.x0 + (bx + i) * pts.dx, pts.y0 - (by + j) * pts.dy))
            (ax, ay), (bxx, byy), (cx, cy), (dxx, dyy) = corners
            for j, row in enumerate(rows):
                t = j / ry
                sx, sy = ax + (cx - ax) * t, ay + (cy - ay) * t
                ex, ey = bxx + (dxx - bxx) * t, byy + (dyy - byy) * t
                stx, sty = (ex - sx) / rx, (ey - sy) / rx
                for i, v in enumerate(row):
                    if v:
                        cell = cell_at(sx + stx * i, sy + sty * i)
                        if cell >= 0:
                            d = counts.get(cell)
                            if d is None:
                                d = counts[cell] = {}
                            d[v] = d.get(v, 0) + 1
    return counts


def shares(cnt: dict) -> dict:
    """{class: share}, shares of the points with data (sum 1)."""
    tot = sum(n for k, n in cnt.items() if k in NALCMS)
    return {k: n / tot for k, n in cnt.items() if k in NALCMS} if tot else {}


def group_shares(cnt: dict) -> dict:
    out = dict.fromkeys(GROUPS, 0.0)
    for k, s in shares(cnt).items():
        out[NALCMS[k][1]] += s
    return out


def dominant_cover(cnt: dict) -> int:
    """Map cover id of the land class (water excluded) with the most points; 0 when there is none."""
    land = {k: n for k, n in cnt.items() if k in NALCMS and NALCMS[k][1] != "water"}
    if not land:
        return 0
    best = max(sorted(land), key=lambda k: land[k])
    return NALCMS[best][0]
