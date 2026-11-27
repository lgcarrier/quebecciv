"""communes.json (recherche, fiche de lieu) et placenames/top.json (noms écrits sur la carte) : les 1 282
subdivisions de recensement du Québec (municipalités, réserves, terres réservées, villages nordiques, territoires
non organisés), avec leur nom officiel tel que publié par Statistique Canada."""

from __future__ import annotations

from ..core.quebec import CSD_TYPES
from ..core.store import load_interim, write_web

REQUIRES = ["_world", "_places", "_cities"]
PRODUCES = ["communes.json", "placenames/top.json"]

PLACENAMES_TILE = 500  # map units (unused: every name fits in top.json)


def build() -> None:
    w = load_interim("_world")
    pl = load_interim("_places")
    in_cma = load_interim("_cities")["in_cma"]
    col = {c: k for k, c in enumerate(pl["columns"])}
    states = w["states"]
    from ..core.quebec import REGIONS
    abbr = [REGIONS[s][0] for s in states]
    names = [r[col["name"]] for r in pl["rows"]]
    dup = {n for n in names if names.count(n) > 1}
    rows = []
    for r in pl["rows"]:
        pop, p16, land = r[col["pop"]], r[col["pop2016"]], r[col["land_km2"]]
        kind = CSD_TYPES.get(r[col["type"]], r[col["type"]])
        name = r[col["name"]] + (f" ({kind.lower()})" if r[col["name"]] in dup else "")
        rows.append([
            r[col["uid"]], name, abbr[r[col["state"]]], pop, r[col["cell"]], in_cma.get(r[col["uid"]]),
            round(pop / land) if pop is not None and land else None, r[col["cd"]],
            int(round(r[col["x"]])), int(round(r[col["y"]])), kind,
            round(pop / p16 - 1, 4) if pop and p16 else None,
        ])
    rows.sort(key=lambda r: (r[2], r[1]))
    write_web("communes.json", {
        "version": 1, "vintage": "Statistique Canada, Recensement de 2021 (subdivisions de recensement)",
        "columns": ["code", "name", "dep", "pop", "cell", "aav", "density", "region", "x", "y", "kind", "growth"],
        "rows": rows,
    })
    top = sorted(([r[0], r[1], r[2], r[3] or 0, r[8], r[9]] for r in rows), key=lambda r: -r[3])
    write_web("placenames/top.json", {"version": 1, "top_min": 0, "tile": PLACENAMES_TILE, "tiles": [],
                                       "columns": ["code", "name", "dep", "pop", "x", "y"], "rows": top})
    print(f"    {len(rows)} places ({len(dup)} homonymous names disambiguated by their type)")
