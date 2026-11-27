"""Couverture du sol du Canada 2020 (RNCan, Centre canadien de cartographie et d'observation de la Terre).

Une image GeoTIFF de 30 m (2,1 Go, LZW, tuiles de 512 px, projection conique conforme de Lambert « Canada Atlas
Lambert », NAD83(SCRS)) en 15 classes du système nord-américain NALCMS. Elle est lue avec la bibliothèque standard
(core/geotiff.py) : on garde un pixel sur huit de l'aperçu au 1/2 (60 m) inclus dans le fichier, soit un point tous
les 480 m environ, sur la fenêtre de la carte. Une carte de 5 km par hexagone n'a pas besoin de plus : environ 280
points par hexagone. L'aperçu au 1/2 reproduit la pleine résolution à 96 % près (vérifié sur une tuile) ; un pixel
sur huit est un échantillonnage régulier, sans biais en faveur des classes dominantes.

Le résultat (un octet de classe par point) est compressé (zlib) et encodé en base64 dans data/interim."""

from __future__ import annotations

import base64
import zlib

from ..core import fetch
from ..core.geotiff import TiledTiff
from ..core.quebec import BBOX
from ..core.source import Source, SourceInfo
from .atlas_water import LambertConformalConic

URL = "https://datacube-prod-data-public.s3.ca-central-1.amazonaws.com/store/land/landcover/landcover-2020-classification.tif"
FILE = "landcover-2020-classification.tif"
LEVEL = 1  # aperçu au 1/2 (60 m)
STRIDE = 8  # un pixel sur 8 : 480 m

# Classes de la couverture du sol du Canada 2020 (index des classes de RNCan, ClassIndex_v2.pdf ; noms français
# de RNCan). Couleurs : celles de la légende officielle (fichier .tif).
CLASSES = {
    1: ("Forêt de conifères sempervirente tempérée ou subpolaire", "#003d00"),
    2: ("Forêt de conifères (taïga) subpolaire", "#949c70"),
    5: ("Forêt feuillue tempérée ou subpolaire", "#148c3d"),
    6: ("Forêt mixte", "#5c752b"),
    8: ("Arbustaie tempérée ou subpolaire", "#b38a33"),
    10: ("Prairie tempérée ou subpolaire", "#e0cf8a"),
    11: ("Arbustaie à lichens et à mousses polaire ou subpolaire", "#9c7554"),
    12: ("Prairie à lichens et à mousses polaire ou subpolaire", "#bad48f"),
    13: ("Lande à lichens et à mousses polaire ou subpolaire", "#408a73"),
    14: ("Milieu humide", "#6ba38a"),
    15: ("Terre cultivée", "#e6ad66"),
    16: ("Lande", "#a8abae"),
    17: ("Milieu urbain", "#dc2126"),
    18: ("Eau", "#4c70a3"),
    19: ("Neige et glace", "#fffaff"),
}


def window(lcc, bbox=BBOX, n=40):
    """Rectangle (x0, y0, x1, y1) in the projection that holds the lon/lat window (its edges, densified)."""
    lon0, lat0, lon1, lat1 = bbox
    pts = []
    for k in range(n + 1):
        t = k / n
        lon, lat = lon0 + (lon1 - lon0) * t, lat0 + (lat1 - lat0) * t
        pts += [lcc.forward(lon, lat0), lcc.forward(lon, lat1), lcc.forward(lon0, lat), lcc.forward(lon1, lat)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


class NrcanLandcover(Source):
    optional = True  # 2,1 Go : `pipeline --light` s'en passe (la carte est alors bâtie sans couverture du sol)
    info = SourceInfo(
        id="nrcan_landcover",
        title="Couverture du sol du Canada 2020 (30 m)",
        publisher="Ressources naturelles Canada (Centre canadien de cartographie et d'observation de la Terre)",
        homepage="https://open.canada.ca/data/fr/dataset/ee1580ab-a23d-4f86-a09b-79763677eb47",
        license="Licence du gouvernement ouvert – Canada",
        description="Carte de la couverture du sol du Canada à 30 m tirée des images Landsat (OLI) de 2019 à 2021, en 15 "
        "classes du Système nord-américain de surveillance des changements de la couverture terrestre (NALCMS) : "
        "forêts de conifères, taïga, feuillus, forêt mixte, arbustaies, prairies, toundra à lichens et mousses, "
        "milieux humides, terres cultivées, landes, milieu urbain, eau, neige et glace. Exactitude globale annoncée "
        "par RNCan : 86,9 % (832 points de contrôle). Contient de l'information visée par la Licence du "
        "gouvernement ouvert – Canada.",
        used_for=["Couverture du sol des hexagones", "Lentilles Forêt, Terres agricoles, Milieux humides, Bâti"],
    )

    def fetch(self, force=False):
        path = self.download(URL, FILE, force=force, expect_binary=True)
        if FILE not in fetch.read_manifest(self.id):  # fichier déjà en cache sans entrée : sha256 calculé ici
            fetch.record(self.id, FILE, URL)
        return path

    def process(self):
        tif = TiledTiff(self.raw_dir / FILE)
        full, lvl = tif.levels[0], tif.levels[LEVEL]
        sx, sy = tif.pixel_scale[0], tif.pixel_scale[1]
        X0, Y0 = tif.tiepoint[3], tif.tiepoint[4]
        rx, ry = sx * full.width / lvl.width, sy * full.height / lvl.height  # taille d'un pixel de l'aperçu
        x0, y0, x1, y1 = window(LambertConformalConic())
        c0, c1 = max(0, int((x0 - X0) / rx)), min(lvl.width, int((x1 - X0) / rx) + 1)
        r0, r1 = max(0, int((Y0 - y1) / ry)), min(lvl.height, int((Y0 - y0) / ry) + 1)
        c0, r0 = c0 - c0 % STRIDE, r0 - r0 % STRIDE
        cols = list(range(c0, c1, STRIDE))
        rows = list(range(r0, r1, STRIDE))
        w, h = len(cols), len(rows)
        out = bytearray(w * h)
        tw, th = lvl.tile_w, lvl.tile_h
        for ty in range(r0 // th, (r1 - 1) // th + 1):
            trows = [(k, r - ty * th) for k, r in enumerate(rows) if ty * th <= r < (ty + 1) * th]
            if not trows:
                continue
            for tx in range(c0 // tw, (c1 - 1) // tw + 1):
                tcols = [(k, c - tx * tw) for k, c in enumerate(cols) if tx * tw <= c < (tx + 1) * tw]
                if not tcols:
                    continue
                tile = tif.read_tile(lvl, tx, ty)
                k0, kc = tcols[0][0], len(tcols)
                lc0 = tcols[0][1]
                for k, lr in trows:
                    out[k * w + k0:k * w + k0 + kc] = tile[lr * tw + lc0: lr * tw + lc0 + (kc - 1) * STRIDE + 1: STRIDE]
        tif.close()
        counts = [0] * 256
        for v in out:
            counts[v] += 1
        print(f"    {w} × {h} points at {rx * STRIDE:.0f} m; classes {[(k, counts[k]) for k in range(256) if counts[k]]}")
        return {
            "vintage": "Couverture du sol du Canada 2020 (images Landsat 2019-2021)",
            "_files": [FILE],
            "crs": "NAD83(CSRS) / Canada Atlas Lambert (EPSG:3979)",
            "x0": X0 + (c0 + 0.5) * rx, "y0": Y0 - (r0 + 0.5) * ry,  # centre du premier point
            "dx": rx * STRIDE, "dy": ry * STRIDE, "width": w, "height": h,
            "classes": {str(k): {"name": v[0], "color": v[1]} for k, v in CLASSES.items()},
            "data_zlib_b64": base64.b64encode(zlib.compress(bytes(out), 9)).decode("ascii"),
        }
