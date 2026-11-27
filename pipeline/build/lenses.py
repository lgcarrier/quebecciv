"""lenses.json et lenses/<id>.json : les lentilles de la carte. Seulement ce que les données réelles permettent :

* `density` : habitants par km² de terre, par hexagone (population des SDR répartie au prorata de leur superficie,
  voir places.py ; superficie terrestre de l'hexagone = sa part de points dans une SDR × 65 km²) ;
* `growth` : variation de la population 2016-2021, par hexagone (mêmes répartitions, SDR qui ont les deux chiffres ;
  null sous GROWTH_MIN_POP habitants en 2016 pour ne pas colorer des variations sur une poignée de personnes) ;
* `forest`, `farmland`, `wetland`, `developed` : part des points de la couverture du sol du Canada 2020 (RNCan) de
  l'hexagone dans un groupe de classes (voir core/landcover.py), eau comprise dans le total."""

from __future__ import annotations

import math

from ..core import landcover
from ..core.quebec import HEX_RADIUS_KM
from ..core.store import load_interim, write_web

REQUIRES = ["_world", "_places"]
PRODUCES = ["lenses.json"]

GROWTH_MIN_POP = 50
MIN_LAND_SHARE = 0.1  # une cellule côtière compte au moins 10 % de terre (évite des densités absurdes)
HEX_KM2 = 3 * math.sqrt(3) / 2 * HEX_RADIUS_KM ** 2


COVER_LENSES = [
    {"id": "forest", "name": "Forêt", "icon": "l-forest", "groups": ["forest"],
     "ramp": ["#f3efe0", "#d4e2b4", "#9cc47f", "#5f9a55", "#2f6b3a", "#173f25"],
     "description": "Part des points de l'hexagone en forêt : conifères, taïga, feuillus et forêt mixte (classes "
     "NALCMS 1, 2, 5 et 6 de la couverture du sol du Canada 2020). L'eau compte dans le total. Les coupes et brûlis "
     "qui se reboisent sont classés en arbustaie, donc hors de la forêt."},
    {"id": "farmland", "name": "Terres agricoles", "icon": "l-farmland", "groups": ["crop"],
     "ramp": ["#f5f1e6", "#efdcae", "#e3bf74", "#cf9a3f", "#a8701f", "#6f4410"],
     "description": "Part des points de l'hexagone en terre cultivée (classe NALCMS 15). Les prairies et pâturages "
     "(classe 10, prairie) n'en font pas partie : la classe ne distingue pas le foin d'une prairie naturelle."},
    {"id": "wetland", "name": "Milieux humides", "icon": "l-wetland", "groups": ["wetland"],
     "ramp": ["#f2f1ea", "#cfe3dc", "#94c6b6", "#5a9f8c", "#2f7564", "#174a3e"],
     "description": "Part des points de l'hexagone en milieu humide (classe NALCMS 14 : tourbières, marais, "
     "marécages). À 30 m, les petits milieux humides boisés passent souvent pour de la forêt."},
    {"id": "developed", "name": "Bâti", "icon": "l-developed", "groups": ["developed"],
     "ramp": ["#f3f1ee", "#e3d6d0", "#cfa99b", "#b8735f", "#93402f", "#5c1a12"],
     "description": "Part des points de l'hexagone en milieu urbain et bâti (classe NALCMS 17 : surfaces "
     "imperméables, bâtiments, routes)."},
]


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
    values = {"density": density, "growth": growth}
    cover = {int(c): {int(k): v for k, v in cnt.items()} for c, cnt in w["cover_counts"].items()}
    for spec in COVER_LENSES:
        vals = [None] * n
        for c, cnt in cover.items():
            gs = landcover.group_shares(cnt)
            vals[c] = round(sum(gs[g] for g in spec["groups"]), 3)
        values[spec["id"]] = vals
        lenses.append({
            "id": spec["id"], "group": "land", "name": spec["name"], "icon": spec["icon"],
            "unit": "part de la superficie de l'hexagone", "format": "pct", "scale": "linear", "domain": [0, 1],
            "ramp": spec["ramp"], "higher_is": "neutral", "source": "nrcan_landcover",
            "note": "Couverture du sol du Canada 2020 (RNCan, 30 m), un point tous les 480 m.",
            "description": spec["description"], "file": f"lenses/{spec['id']}"})
    for lens in lenses:
        write_web(f"lenses/{lens['id']}.json", {"id": lens["id"], "values": values[lens["id"]]})
    write_web("lenses.json", {
        "vintage": "Statistique Canada, Recensement de 2021 (et 2016) ; RNCan, couverture du sol du Canada 2020",
        "groups": [{"id": "people", "name": "Population"}, {"id": "land", "name": "Territoire"}],
        "lenses": lenses,
    })
    print(f"    density domain {lenses[0]['domain']}, growth domain {lenses[1]['domain']}; "
          f"cover lenses {[sp['id'] for sp in COVER_LENSES]}")
