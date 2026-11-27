"""cities.json : les villes de la carte.

* Les régions métropolitaines de recensement (RMR) et agglomérations de recensement (AR) de 2021 (tableau
  98-10-0003-01), l'équivalent canadien des « aires urbaines fonctionnelles » d'Eurostat : un noyau urbain et les
  municipalités qui y sont fortement intégrées par les déplacements domicile-travail. Pour une RMR/AR à cheval sur
  une frontière (Ottawa–Gatineau, Campbellton, Hawkesbury), seule la partie québécoise compte, et elle n'est gardée
  que si elle a au moins CITY_PART_MIN habitants.
* Les municipalités (SDR) de TOWN_MIN habitants ou plus qui ne font partie d'aucune RMR/AR.

La population est celle du Recensement de 2021 (somme des SDR québécoises membres, égale au chiffre publié de la
RMR/AR quand elle est entièrement au Québec). Aucune donnée économique (rendements, emplois, PIB) n'est encore
attachée : ces champs restent null."""

from __future__ import annotations

import math

from ..core.hexgrid import HexGrid
from ..core.quebec import CAPITAL_CSD, CITY_PART_MIN, CSD_TYPES, METRO_MIN, PRUID, REGIONS, TOWN_MIN
from ..core.store import load_interim, save_interim, write_web

REQUIRES = ["_world", "_places", "statcan_population"]
PRODUCES = ["cities.json", "_cities"]


def _growth(p21, p16):
    return round(p21 / p16 - 1, 4) if p21 and p16 else None


def _de(name: str) -> str:
    """« de Montréal », mais « d'Ottawa » (élision devant une voyelle ou un h muet)."""
    return f"d'{name}" if name[:1].lower() in "aeiouyéèêàâîôûh" else f"de {name}"


def build() -> None:
    w = load_interim("_world")
    pl = load_interim("_places")
    sp = load_interim("statcan_population")
    grid = HexGrid(**w["grid"])
    owner = w["owner"]
    col = {c: k for k, c in enumerate(pl["columns"])}
    places = {r[col["uid"]]: r for r in pl["rows"]}
    states = w["states"]
    state_abbr = {k: REGIONS[s][0] for k, s in enumerate(states)}  # ERUID → numéro de région (« 06 »)
    world_states = None

    # Cells where a member SDR has the majority of the cell's samples (footprints).
    majority = {}
    for k, cells in w["csd_cells"].items():
        for c, n, _, _ in cells:
            if owner[c] >= 0 and n > majority.get(c, (None, 0))[1]:
                majority[c] = (w["csd"][int(k)], n)
    cells_of = {}
    for c, (uid, _) in majority.items():
        cells_of.setdefault(uid, []).append(c)

    cities = []
    in_cma = {}
    for uid, cma in sp["cma"].items():
        members = [m for m in cma["members"] if m.startswith(PRUID)]
        others = [m for m in cma["members"] if not m.startswith(PRUID)]
        p21 = sum(places[m][col["pop"]] or 0 for m in members)
        both = [m for m in members if places[m][col["pop"]] is not None and places[m][col["pop2016"]] is not None]
        p16 = sum(places[m][col["pop2016"]] for m in both)
        p21b = sum(places[m][col["pop"]] for m in both)
        if p21 < CITY_PART_MIN:
            continue
        cid = f"{cma['kind']}{uid}"
        for m in members:
            in_cma[m] = cid
        core = max(members, key=lambda m: places[m][col["pop"]] or 0)
        cross = bool(others)
        kind = "région métropolitaine de recensement" if cma["kind"] == "RMR" else "agglomération de recensement"
        name = cma["name"].replace(" - ", "–")
        cities.append({
            "id": cid, "name": name + (" (Qc)" if cross else ""),
            "full": f"{kind.capitalize()} {_de(name)}" + (" (partie québécoise)" if cross else ""),
            "kind": cma["kind"], "members": members, "core": core, "cross_border": cross,
            "population": p21, "population_total": cma["pop2021"] if cross else p21,
            "growth": _growth(p21b, p16),
        })
    for uid, r in places.items():
        if uid in in_cma or (r[col["pop"]] or 0) < TOWN_MIN:
            continue
        p21, p16 = r[col["pop"]], r[col["pop2016"]]
        cities.append({
            "id": f"SDR{uid}", "name": r[col["name"]],
            "full": f"{r[col['name']]} ({CSD_TYPES.get(r[col['type']], r[col['type']]).lower()}, hors RMR et AR)",
            "kind": "SDR", "members": [uid], "core": uid, "cross_border": False,
            "population": p21, "population_total": p21, "growth": _growth(p21, p16),
        })
    cities.sort(key=lambda c: -c["population"])

    taken = set()
    out = []
    for c in cities:
        core = places[c["core"]]
        cell = core[col["cell"]]
        if cell in taken:  # a bigger city holds it: the nearest free Québec cell within 2 rings
            ring, seen = [cell], {cell}
            found = None
            for _ in range(2):
                nxt = []
                for x in ring:
                    for n in grid.neighbours(x):
                        if n not in seen:
                            seen.add(n)
                            nxt.append(n)
                free = [n for n in nxt if owner[n] >= 0 and n not in taken]
                if free:
                    found = free[0]
                    break
                ring = nxt
            cell = found if found is not None else cell
        taken.add(cell)
        footprint = sorted({x for m in c["members"] for x in cells_of.get(m, [])} | {cell})
        land = sum(places[m][col["land_km2"]] or 0 for m in c["members"])
        regions = []
        for m in sorted(c["members"], key=lambda m: -(places[m][col["pop"]] or 0)):
            ab = state_abbr[places[m][col["state"]]]
            if ab not in regions:
                regions.append(ab)
        out.append({
            "id": c["id"], "name": c["name"], "full": c["full"], "local_name": None,
            "states": regions, "metro": c["population"] >= METRO_MIN,
            "capital": CAPITAL_CSD in c["members"], "national_capital": CAPITAL_CSD in c["members"],
            "centre": core[col["name"]], "centre_code": c["core"],
            "commune_population": core[col["pop"]], "commune_year": 2021,
            "x": core[col["x"]], "y": core[col["y"]], "cell": cell,
            "population": c["population"], "population_total": c["population_total"],
            "cross_border": c["cross_border"], "kind": c["kind"],
            "growth": c["growth"], "growth_years": [2016, 2021],
            "municipalities": len(c["members"]), "members": c["members"],
            "counties": sorted({m[:4] for m in c["members"]}),
            "land_km2": round(land, 1), "density": round(c["population"] / land, 1) if land else None,
            "footprint": footprint,
            "yields": None, "jobs": None, "employed": None, "gdp": None, "gdp_per_capita": None,
            "estimated": None, "band": None, "communes": None,
            "source": "statcan_population",
        })
    # ranks and peers
    by_pop = sorted(out, key=lambda c: -c["population"])
    rank = {c["id"]: k + 1 for k, c in enumerate(by_pop)}
    gr = sorted([c for c in out if c["growth"] is not None], key=lambda c: -c["growth"])
    grank = {c["id"]: k + 1 for k, c in enumerate(gr)}
    for c in out:
        c["ranks"] = {"population": rank[c["id"]], "growth": grank.get(c["id"])}
        c["peers"] = [p["id"] for p in sorted((p for p in out if p is not c),
                                               key=lambda p: abs(math.log(p["population"] / c["population"])))[:5]]
    print(f"    {len(out)} cities: {sum(1 for c in out if c['kind'] != 'SDR')} RMR/AR, "
          f"{sum(1 for c in out if c['kind'] == 'SDR')} towns of {TOWN_MIN:,}+ outside them")
    write_web("cities.json", out)
    save_interim("_cities", {"in_cma": in_cma})
