"""lenses.json et lenses/<id>.json : les lentilles de la carte. Seulement ce que les données réelles permettent :

* `density` : habitants par km² de terre, par hexagone (population des SDR répartie au prorata de leur superficie,
  voir places.py ; superficie terrestre de l'hexagone = sa part de points dans une SDR × 65 km²) ;
* `growth` : variation de la population 2016-2021, par hexagone (mêmes répartitions, SDR qui ont les deux chiffres ;
  null sous GROWTH_MIN_POP habitants en 2016 pour ne pas colorer des variations sur une poignée de personnes)."""

from __future__ import annotations

import math

from ..core.quebec import HEX_RADIUS_KM
from ..core.store import load_interim, write_web

REQUIRES = ["_world", "_places"]
PRODUCES = ["lenses.json"]

GROWTH_MIN_POP = 50
MIN_LAND_SHARE = 0.1  # une cellule côtière compte au moins 10 % de terre (évite des densités absurdes)
HEX_KM2 = 3 * math.sqrt(3) / 2 * HEX_RADIUS_KM ** 2


def round2(v, up):
    """Round to two significant digits, outward (up=True rounds up)."""
    if v == 0:
        return 0
    mag = 10 ** (math.floor(math.log10(abs(v))) - 1)
    return (math.ceil(v / mag) if up else math.floor(v / mag)) * mag


def pctile(vals, q):
    s = sorted(vals)
    return s[min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))]


def build() -> None:
    w = load_interim("_world")
    pl = load_interim("_places")
    owner = w["owner"]
    ns = w["samples_per_cell"]
    n = len(owner)
    density, growth = [None] * n, [None] * n
    for i in range(n):
        if owner[i] < 0:
            continue
        land = max(w["land_samples"][i] / ns, MIN_LAND_SHARE) * HEX_KM2
        density[i] = round(pl["hexpop"][i] / land, 2)
        if pl["hexpop16"][i] >= GROWTH_MIN_POP:
            growth[i] = round(pl["hexpop21b"][i] / pl["hexpop16"][i] - 1, 4)

    # La moitié des hexagones du Québec sont inhabités (Nord) : le domaine de la densité se calcule sur les hexagones
    # habités (5e et 99,5e centiles), sinon toute la vallée du Saint-Laurent prendrait la couleur maximale.
    dvals = [v for v in density if v is not None and v > 0]
    gvals = [v for v in growth if v is not None]
    lo, hi = round2(pctile(dvals, 0.05), False), round2(pctile(dvals, 0.995), True)
    g = max(abs(round2(pctile(gvals, 0.02), False)), abs(round2(pctile(gvals, 0.98), True)))
    lenses = [
        {"id": "density", "group": "people", "name": "Densité de population", "icon": "l-density",
         "unit": "habitants par km² de terre", "format": "int", "scale": "log", "domain": [max(lo, 0.001), hi],
         "ramp": ["#1a1033", "#3b1f6b", "#6a2c8c", "#a2407a", "#d6614f", "#f39c3c", "#fbe38c"],
         "higher_is": "neutral", "source": "statcan_population",
         "note": "Approximation : la population de chaque municipalité est répartie uniformément sur sa superficie.",
         "description": "Population du Recensement de 2021 de chaque subdivision de recensement, répartie sur les "
         "hexagones au prorata de sa superficie terrestre, divisée par la superficie terrestre de l'hexagone. Une "
         "grande municipalité rurale ou un territoire non organisé paraît donc uniformément peuplé.",
         "file": "lenses/density"},
        {"id": "growth", "group": "people", "name": "Croissance 2016-2021", "icon": "l-growth",
         "unit": "variation de la population entre les recensements de 2016 et 2021", "format": "change",
         "scale": "linear", "domain": [-g, g],
         "ramp": ["#8c2d04", "#d9603b", "#f4b183", "#f2efe6", "#9ecae1", "#4292c6", "#08519c"],
         "higher_is": "neutral", "source": "statcan_population",
         "note": f"Vide là où moins de {GROWTH_MIN_POP} personnes vivaient en 2016.",
         "description": "Population de 2021 ÷ population de 2016 − 1, des subdivisions de recensement réparties sur "
         "les hexagones comme pour la densité (chiffres de 2016 rajustés aux limites de 2021 par Statistique "
         "Canada). Les réserves sans chiffre publié sont exclues.",
         "file": "lenses/growth"},
    ]
    for lens, vals in ((lenses[0], density), (lenses[1], growth)):
        write_web(f"lenses/{lens['id']}.json", {"id": lens["id"], "values": vals})
    write_web("lenses.json", {
        "vintage": "Statistique Canada, Recensement de 2021 (et 2016)",
        "groups": [{"id": "people", "name": "Population"}],
        "lenses": lenses,
    })
    print(f"    density domain {lenses[0]['domain']}, growth domain {lenses[1]['domain']}")
