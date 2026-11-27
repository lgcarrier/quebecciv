"""states.json (les 17 régions administratives) et nation.json (le Québec dans son ensemble).

Population : somme des SDR de la région (Recensement de 2021) ; croissance 2016-2021 sur les SDR qui ont les deux
chiffres ; superficie terrestre : celle de la région économique dans les limites cartographiques."""

from __future__ import annotations

from ..core.quebec import CSD_TYPES
from ..core.store import load_interim, write_web

REQUIRES = ["_world", "_places", "statcan_boundaries", "statcan_population"]
PRODUCES = ["states.json", "nation.json"]

REGIONAL_LABEL = "Région administrative"


def build() -> None:
    w = load_interim("_world")
    pl = load_interim("_places")
    sb = load_interim("statcan_boundaries")
    sp = load_interim("statcan_population")
    col = {c: k for k, c in enumerate(pl["columns"])}
    er_land = {e["uid"]: e["land_km2"] for e in sb["er"]}
    world = None
    out = []
    from ..core.quebec import REGIONS
    for s, uid in enumerate(w["states"]):
        rows = [r for r in pl["rows"] if r[col["state"]] == s]
        p21 = sum(r[col["pop"]] or 0 for r in rows)
        both = [r for r in rows if r[col["pop"]] is not None and r[col["pop2016"]] is not None]
        p16 = sum(r[col["pop2016"]] for r in both)
        p21b = sum(r[col["pop"]] for r in both)
        land = er_land[uid]
        out.append({
            "fips": uid, "abbr": REGIONS[uid][0], "name": REGIONS[uid][1], "region": "Québec",
            "kind": REGIONAL_LABEL, "capital": None,
            "population": p21, "pop2016": p16 if both else None,
            "growth": round(p21b / p16 - 1, 4) if p16 else None, "growth_years": [2016, 2021],
            "land_km2": round(land, 1), "density": round(p21 / land, 2) if land else None,
            "municipalities": len(rows),
            "not_enumerated": [r[col["name"]] for r in rows if r[col["pop"]] is None],
            "counties": sorted({r[col["cd"]] for r in rows}),
            "label": None, "land": None, "energy": None, "yields": None, "ranks": {},
        })
    for key in ("population", "density", "growth"):
        order = sorted([s for s in out if s[key] is not None], key=lambda s: -s[key])
        for k, s in enumerate(order):
            s["ranks"][key] = k + 1
    write_web("states.json", out)

    prov = sp["province"]
    p21 = sum(r[col["pop"]] or 0 for r in pl["rows"])
    both = [r for r in pl["rows"] if r[col["pop"]] is not None and r[col["pop2016"]] is not None]
    p16 = sum(r[col["pop2016"]] for r in both)
    p21b = sum(r[col["pop"]] for r in both)
    types = {}
    for r in pl["rows"]:
        types[r[col["type"]]] = types.get(r[col["type"]], 0) + 1
    write_web("nation.json", {
        "vintage": "Statistique Canada, Recensement de la population de 2021",
        "year": 2021,
        "gdp_vintage": None,
        "name": "Québec", "countries": len(out), "country_label": "régions administratives",
        "nation": {
            "population": p21, "population_official": prov["pop2021"], "pop2016": prov["pop2016"],
            "growth": round(p21b / p16 - 1, 4), "growth_years": [2016, 2021],
            "land_km2": prov["land_km2"], "density": round(p21 / prov["land_km2"], 2),
            "municipalities": len(pl["rows"]),
            "csd_types": {CSD_TYPES.get(t, t): n for t, n in sorted(types.items(), key=lambda kv: -kv[1])},
            "not_enumerated": [r[col["name"]] for r in pl["rows"] if r[col["pop"]] is None],
        },
        "yields": [], "industries": {}, "gdp_industries": {},
    })
    print(f"    17 régions, Québec {p21:,} habitants (officiel {prov['pop2021']:,})")
