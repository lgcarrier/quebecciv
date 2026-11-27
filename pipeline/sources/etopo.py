"""ETOPO1 (NOAA), relief terrestre et profondeur des mers, lu par ERDDAP sur la fenêtre du Québec."""

from __future__ import annotations

import csv

from ..core.source import Source, SourceInfo

# Un point sur deux (2 minutes d'arc, ~3,7 km nord-sud, ~2 km est-ouest à 55° N), en tranches de longitude.
STRIDE = 2
# Fenêtre : tout le rectangle de la carte (ses coins vont de 86° O à 52° O, de 43,9° N à 63,4° N), en cinq tranches.
LAT = (43.5, 63.7)
SLICES = [(-86.5, -79.5), (-79.5, -72.5), (-72.5, -65.5), (-65.5, -58.5), (-58.5, -51.5)]


def _url(lon):
    return ("https://coastwatch.pfeg.noaa.gov/erddap/griddap/etopo180.csv"
            f"?altitude%5B({LAT[0]}):{STRIDE}:({LAT[1]})%5D%5B({lon[0]}):{STRIDE}:({lon[1]})%5D")


def _file(lon):
    return f"etopo_lat{LAT[0]}_{LAT[1]}_lon{lon[0]}_{lon[1]}_stride{STRIDE}.csv"


class Etopo(Source):
    info = SourceInfo(
        id="etopo",
        title="ETOPO1, modèle mondial du relief",
        publisher="NOAA National Centers for Environmental Information (par ERDDAP)",
        homepage="https://www.ncei.noaa.gov/products/etopo-global-relief-model",
        license="Domaine public (œuvre du gouvernement des États-Unis)",
        description="Altitude des terres et profondeur des mers, un point toutes les deux minutes d'arc. Le relief de "
        "chaque hexagone (plat, collines, montagnes, sommets) vient de la moyenne et de l'écart type de ses points "
        "terrestres ; l'ombrage du relief aussi.",
        used_for=["Relief (collines, montagnes)", "Ombrage", "Profondeur de la mer"],
    )

    def fetch(self, force=False):
        for lo in SLICES:
            self.download(_url(lo), _file(lo), force=force)

    def process(self):
        lat, lon, alt = [], [], []
        for lo in SLICES:
            with open(self.raw_dir / _file(lo), newline="") as f:
                rows = csv.reader(f)
                next(rows), next(rows)  # en-tête + unités
                for a, o, al in rows:
                    if al == "NaN":
                        continue  # (les tranches voisines partagent leur méridien de bord : quelques doublons, sans effet)
                    lat.append(round(float(a), 4))
                    lon.append(round(float(o), 4))
                    alt.append(int(float(al)))
        return {"vintage": "ETOPO1, 1 minute d'arc (un point sur deux)", "_files": [_file(lo) for lo in SLICES],
                "lat": lat, "lon": lon, "alt": alt}
