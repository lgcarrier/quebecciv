"""Les subdivisions de recensement (SDR) placées sur la carte et leur population répartie sur les hexagones.

* Chaque SDR reçoit un point (la moyenne de ses points d'échantillonnage, ramenée sur l'un d'eux si elle tombe hors
  de la SDR) et un hexagone (celui du point, ou le plus proche hexagone du Québec).
* Sa population de 2021 (et de 2016) est répartie entre les hexagones au prorata de ses points d'échantillonnage,
  donc uniformément sur sa superficie terrestre : c'est une approximation (une grande municipalité rurale ou un
  territoire non organisé est réparti sur tout son territoire, même si les gens vivent au village). La part tombée
  dans un hexagone d'eau ou de voisin reste dans la même municipalité : elle est répartie sur ses autres hexagones du
  Québec. Chaque SDR garde au moins un hexagone de terre (world.py) ; seule une SDR
  trop petite pour un point d'échantillonnage va à l'hexagone de son centre, ou au plus proche s'il est dans l'eau.

Interim `_places` : `columns`/`rows` (une ligne par SDR), `hexpop` et `hexpop16` (par cellule, réels), `hexpop21b` (2021, seulement les SDR qui ont aussi un chiffre de 2016)."""

from __future__ import annotations

import math
from collections import deque

from ..core.hexgrid import HexGrid
from ..core.store import load_interim, save_interim

REQUIRES = ["_world", "statcan_population"]
PRODUCES = ["_places"]

COLUMNS = ["uid", "name", "type", "pop", "pop2016", "land_km2", "x", "y", "cell", "cd", "state"]


def nearest_owned(grid: HexGrid, owner: list, cell: int, max_rings: int = 12) -> int:
    """The cell itself if it is Québec land, else the nearest Québec cell within max_rings (breadth first), or -1."""
    if cell >= 0 and owner[cell] >= 0:
        return cell
    if cell < 0:
        return -1
    seen, q = {cell}, deque([(cell, 0)])
    while q:
        c, d = q.popleft()
        if d >= max_rings:
            continue
        for n in grid.neighbours(c):
            if n in seen:
                continue
            if owner[n] >= 0:
                return n
            seen.add(n)
            q.append((n, d + 1))
    return -1


def build() -> None:
    w = load_interim("_world")
    sp = load_interim("statcan_population")
    grid = HexGrid(**w["grid"])
    owner = w["owner"]
    pops = sp["csd"]
    hexpop = [0.0] * grid.size
    hexpop16 = [0.0] * grid.size
    hexpop21b = [0.0] * grid.size  # 2021 population of the SDR that also have a 2016 count (for growth)
    rows = []
    moved_out = [0.0]  # 2021 residents whose points fell on water/neighbour hexes, kept in their own municipality
    other_sdr = [0]  # SDR with no Québec land hex of their own (their people go to the nearest one)
    other_names = []
    without_own = []  # inhabited SDR whose people are not on a hex of their own
    for k, uid in enumerate(w["csd"]):
        p = pops.get(uid)
        if p is None:
            raise ValueError(f"SDR {uid} absente du tableau 98-10-0002-01")
        cells = w["csd_cells"].get(str(k))
        if cells:
            total = sum(c[1] for c in cells)
            mx = sum(c[2] for c in cells) / total
            my = sum(c[3] for c in cells) / total
            cell_set = {c[0] for c in cells}
            cell = grid.cell_at(mx, my)
            if cell not in cell_set:  # concave SDR: use the sample mean of its cell nearest to the centroid
                best = min(cells, key=lambda c: (c[2] / c[1] - mx) ** 2 + (c[3] / c[1] - my) ** 2)
                mx, my, cell = best[2] / best[1], best[3] / best[1], best[0]
            # Only the SDR's own Québec land hexes receive its population (pro rata of their points); the share of
            # its points that fell in hexes now water or a neighbour's stays in the same municipality. Only an SDR
            # with no Québec land hex at all sends it to the nearest Québec hex.
            owned = [c for c in cells if owner[c[0]] >= 0]
            if owned:
                spread = [(c[0], c[1]) for c in owned]
                moved_out[0] += sum(c[1] for c in cells if owner[c[0]] < 0) / total * (p["pop2021"] or 0)
            else:
                spread = []
                for c, n, _, _ in cells:
                    tgt = nearest_owned(grid, owner, c)
                    if tgt < 0:
                        raise ValueError(f"SDR {uid} : aucun hexagone du Québec près de la cellule {c}")
                    spread.append((tgt, n))
                other_sdr[0] += 1
                other_names.append(f"{p['name']} ({p['pop2021']})")
                if p["pop2021"]:
                    without_own.append(uid)
            tot = sum(n for _, n in spread)
            for tgt, n in spread:
                if p["pop2021"] is not None:
                    hexpop[tgt] += p["pop2021"] * n / tot
                if p["pop2021"] is not None and p["pop2016"] is not None:
                    hexpop16[tgt] += p["pop2016"] * n / tot
                    hexpop21b[tgt] += p["pop2021"] * n / tot
        else:
            mx, my = w["csd_point"][str(k)]
            cell = grid.cell_at(mx, my)
            tgt = nearest_owned(grid, owner, cell)
            if tgt < 0:  # (hexpop[-1] would silently put its people on the last hex of the grid)
                raise ValueError(f"SDR {uid} : aucun hexagone du Québec près de son centre (cellule {cell})")
            if tgt != cell and p["pop2021"]:
                other_sdr[0] += 1
                other_names.append(f"{p['name']} ({p['pop2021']})")
                without_own.append(uid)
            if p["pop2021"] is not None:
                hexpop[tgt] += p["pop2021"]
            if p["pop2021"] is not None and p["pop2016"] is not None:
                hexpop16[tgt] += p["pop2016"]
                hexpop21b[tgt] += p["pop2021"]
        cell = nearest_owned(grid, owner, cell)
        rows.append([uid, p["name"], w["csd_type"][k], p["pop2021"], p["pop2016"], p["land_km2"],
                     round(mx, 1), round(my, 1), cell, uid[:4], w["csd_state"][k]])
    total = sum(hexpop)
    official = sp["province"]["pop2021"]
    print(f"    {len(rows)} SDR; population on the hexes {total:,.0f} (official Québec total {official:,}); "
          f"{moved_out[0]:,.0f} residents moved off water/neighbour hexes within their municipality; "
          f"{other_sdr[0]} SDR placed on the nearest Québec hex")
    if other_names:
        print("      (" + ", ".join(other_names) + ")")
    if abs(total - official) > 1:
        raise ValueError("la population répartie ne correspond pas au total officiel")
    save_interim("_places", {"columns": COLUMNS, "rows": rows,
                             "hexpop": [round(v, 2) for v in hexpop], "hexpop16": [round(v, 2) for v in hexpop16],
                             "hexpop21b": [round(v, 2) for v in hexpop21b], "without_own_hex": without_own})
