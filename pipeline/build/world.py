"""La carte elle-même : grille d'hexagones, terre et eau, relief, régions administratives, MRC, rivières.

Méthode (tout en km de la projection équivalente, core/quebec.py) :

* les 1 282 subdivisions de recensement (SDR) du Québec, les provinces voisines, les États-Unis, les lacs de Natural
  Earth et les 17 régions économiques sont rastérisés à RASTER_KM (0,5 km) ;
* chaque hexagone lit ce raster en environ 80 points d'échantillonnage répartis sur une maille de 1 km ;
* un hexagone appartient au Québec, à un voisin ou à l'eau selon la majorité de ses points (le centre départage) ;
  sa région administrative et sa MRC sont celles de la SDR sous son centre, sinon de la SDR la plus présente ;
* la part de chaque SDR dans chaque hexagone est gardée (interim `_world`) pour répartir la population.

Interim `_world` : grid, projection, owner, county, water, states (codes RÉ), counties (codes DR), csd (codes SDR),
`csd_cells` (par SDR : [[cellule, nb de points, somme x, somme y], …]), `csd_point` (point de repli des SDR sans
point d'échantillonnage), land_samples (par cellule), samples_per_cell."""

from __future__ import annotations

import math
from collections import Counter, defaultdict, deque

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.quebec import (BBOX, CSD_TYPES, HEX_RADIUS_UNITS, MARGIN_UNITS, PRUID, REGIONS, SCALE)
from ..core.raster import Raster
from ..core.store import load_interim, save_interim, write_web

REQUIRES = ["statcan_boundaries", "natural_earth", "etopo", "atlas_water"]
PRODUCES = ["world.json", "_world"]

RASTER_KM = 0.5
SAMPLE_KM = 1.0
LAND, OCEAN, COAST, LAKE = range(4)
FOREIGN, WATER_CELL = -2, -1
COAST_DEPTH_M = -200
FLAT, HILLS, MOUNTAINS, PEAKS = range(4)
# Hexagones de 5 km de rayon : seuils d'écart type plus bas que ceux d'europeciv (10 km) pour un même terrain.
HILLS_STD, MOUNTAINS_STD, MOUNTAINS_MEAN, PEAKS_MEAN = 40, 140, 900, 1400
LAND_MIN_ALT_M = -100
RIVER_MAX_RANK = 12  # Natural Earth scalerank (1 = le plus important)
# Grands cours d'eau : le Saint-Laurent fluvial (1 à 3 km de large entre Montréal et Québec), l'Outaouais, le fjord du
# Saguenay… sont plus étroits qu'un hexagone (8,7 km d'un côté à l'autre) : à la majorité des points, ils
# disparaîtraient. Une étendue d'eau de l'Atlas est « fluviale » si elle couvre au moins RIVER_MIN_KM2 et qu'elle est
# allongée (portée² / superficie ≥ RIVER_ELONGATION : environ 12 pour le Saint-Laurent fluvial, 40 pour le Saguenay,
# 3 à 4 pour un lac rond comme le lac Saint-Pierre).
RIVER_MIN_KM2 = 30.0
RIVER_ELONGATION = 10.0
RIVER_MIN_WATER = 0.35
RIVER_COURSE_KM2 = 60.0  # au-delà, le cours d'eau est tracé d'un bout à l'autre, même où il est plus étroit
WB_LAKE, WB_RIVER = 1, 2
SEA_LINK_MIN_HEXES = 20  # a joined river network this long (in hexes) is also linked to the sea…
SEA_LINK_STEPS = 6  # …when the sea is at most this many steps away
SEA_RIVERS = {"Fleuve Saint-Laurent"}  # Atlas water bodies joined to the sea (not counted as lakes)
RIVER_STEP_KM = 0.5

WATER_TABLE = [
    {"id": LAND, "name": "Terre", "rule": "La majorité des points d'échantillonnage de l'hexagone (environ 80, "
     "maille de 1 km) tombent dans une subdivision de recensement du Québec ou chez un voisin (limites "
     "cartographiques de Statistique Canada ; Natural Earth pour les États-Unis)."},
    {"id": OCEAN, "name": "Mer", "color": "#1b4266", "rule": "Eau reliée au bord de la carte, plus profonde que "
     "200 m (moyenne ETOPO1) et loin de la terre."},
    {"id": COAST, "name": "Côte", "color": "#2d6d97", "rule": "Eau reliée au bord de la carte, voisine d'une terre "
     "ou moins profonde que 200 m (moyenne ETOPO1). Le fleuve Saint-Laurent et le Saguenay en font partie."},
    {"id": LAKE, "name": "Lac", "color": "#3a80b0", "rule": "Eau dont la majorité des points tombent dans un lac de "
     "Natural Earth 1:10m, ou eau intérieure qui ne rejoint pas le bord de la carte (lacs et réservoirs)."},
]
WATER_NOTE = ("Les eaux intérieures (fleuve, rivières larges, lacs) viennent des étendues d'eau de l'Atlas du Canada "
              "au 1:1 000 000 : les limites de Statistique Canada les laissent dans les municipalités. Le long des "
              "grands cours d'eau plus étroits qu'un hexagone (Saint-Laurent fluvial, Outaouais, Saguenay…), un "
              f"hexagone devient de l'eau dès que {round(RIVER_MIN_WATER * 100)} % de ses points y tombent ; les "
              "tronçons sont ensuite reliés par les hexagones les plus mouillés, et le fleuve jusqu'à l'estuaire, pour "
              "que le cours d'eau reste continu. Il paraît donc plus large qu'en réalité. Une municipalité dont aucun "
              "hexagone n'est resté de la terre reçoit celui où elle a le plus de points, sauf s'il porte le cours "
              "d'eau : sa population va alors à l'hexagone québécois le plus proche.")
RELIEF_TABLE = [
    {"id": FLAT, "name": "Plat", "rule": f"Écart type de l'altitude dans l'hexagone inférieur à {HILLS_STD} m."},
    {"id": HILLS, "name": "Collines", "rule": f"Écart type de l'altitude ≥ {HILLS_STD} m."},
    {"id": MOUNTAINS, "name": "Montagnes", "rule": f"Écart type ≥ {MOUNTAINS_STD} m, ou altitude moyenne ≥ {MOUNTAINS_MEAN} m."},
    {"id": PEAKS, "name": "Sommets", "rule": f"Altitude moyenne ≥ {PEAKS_MEAN} m."},
]
RELIEF_NOTE = ("Des points ETOPO1 (un toutes les deux minutes d'arc, une dizaine par hexagone) à -100 m ou plus ; "
               "tous les points s'il n'y en a aucun. Les hexagones d'eau sont toujours plats.")
COVER_TABLE = [{"id": 0, "key": "none", "name": "Non disponible", "rule": "Pas encore de couverture du sol : la "
                "couleur de la terre suit l'altitude."}]
COVER_NOTE = ("La couverture du sol (forêt, cultures, milieux humides…) n'est pas encore intégrée : la terre est "
              "colorée selon l'altitude. Source prévue : la couverture du sol du Canada de RNCan (30 m).")

# Noms de mers et de reliefs écrits sur la carte : (nom, type, lon, lat, hauteur de police en km, angle).
# Les positions des étendues d'eau sont vérifiées au build (elles doivent tomber sur un hexagone d'eau).
GEO_LABELS = [
    ("Baie d'Hudson", "sea", -79.3, 59.0, 22, -70),
    ("Détroit d'Hudson", "sea", -70.5, 62.4, 14, -10),
    ("Baie d'Ungava", "sea", -67.6, 59.6, 14, 0),
    ("Baie James", "sea", -80.3, 53.2, 11, -80),
    ("Golfe du Saint-Laurent", "sea", -61.8, 48.4, 18, 0),
    ("Mer du Labrador", "sea", -57.5, 57.5, 18, -55),
    ("Estuaire du Saint-Laurent", "sea", -68.3, 48.9, 9, -30),
]


def hex_offsets(radius_km: float, step_km: float) -> list[tuple[float, float]]:
    """Points of a square lattice (spacing step_km) inside a pointy-top hex of the given radius, centre first."""
    out = [(0.0, 0.0)]
    n = int(radius_km // step_km) + 1
    half_w = math.sqrt(3) / 2 * radius_km
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            dx, dy = i * step_km, j * step_km
            if (dx, dy) == (0.0, 0.0):
                continue
            if abs(dx) <= half_w and abs(dy) <= radius_km - abs(dx) / math.sqrt(3):
                out.append((dx, dy))
    return out


def ring_area_km2(ring) -> float:
    return abs(sum(ring[k - 1][0] * ring[k][1] - ring[k][0] * ring[k - 1][1] for k in range(len(ring)))) / 2


def is_river_like(rings_km) -> float:
    """A large, elongated water body (km coordinates): area ≥ RIVER_MIN_KM2 and span² / area ≥ RIVER_ELONGATION.
    Returns its area in km² (0 if not river-like)."""
    outer = max(rings_km, key=len)
    area = ring_area_km2(outer) - sum(ring_area_km2(r) for r in rings_km if r is not outer)
    if area < RIVER_MIN_KM2:
        return 0.0
    xs, ys = [p[0] for p in outer], [p[1] for p in outer]
    span = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
    return area if span * span / area >= RIVER_ELONGATION else 0.0


def course(grid, cand: set, share: list) -> set:
    """The wettest chain of hexes between the two ends of a water body (its two hexes farthest apart, in steps)."""
    import heapq

    def farthest(start):
        dist, q = {start: 0}, [start]
        for x in q:
            for n in grid.neighbours(x):
                if n in cand and n not in dist:
                    dist[n] = dist[x] + 1
                    q.append(n)
        return max(dist, key=dist.get)

    a = farthest(min(cand))
    b = farthest(a)
    dist, prev, heap = {a: 0.0}, {}, [(0.0, a)]
    while heap:
        d, x = heapq.heappop(heap)
        if x == b:
            break
        if d > dist[x]:
            continue
        for n in grid.neighbours(x):
            if n in cand:
                nd = d + (1.05 - min(1.0, share[n]))
                if nd < dist.get(n, 1e18):
                    dist[n], prev[n] = nd, x
                    heapq.heappush(heap, (nd, n))
    out, x = {b}, b
    while x in prev:
        x = prev[x]
        out.add(x)
    return out


def components(grid, cells: set) -> list[set]:
    """Connected pieces of a set of hexes."""
    seen, res = set(), []
    for c in cells:
        if c in seen:
            continue
        comp, stack = set(), [c]
        seen.add(c)
        while stack:
            x = stack.pop()
            comp.add(x)
            for n in grid.neighbours(x):
                if n in cells and n not in seen:
                    seen.add(n)
                    stack.append(n)
        res.append(comp)
    return res


def link_to_sea(grid, piece: set, sea: set, share: list, max_steps: int) -> set:
    """The wettest chain (cost 1.05 − share) from `piece` to a `sea` hex, through hexes at most `max_steps` steps from
    `piece`; empty when the sea is farther."""
    import heapq

    near, frontier = set(piece), list(piece)
    for _ in range(max_steps):
        nxt = []
        for x in frontier:
            for n in grid.neighbours(x):
                if n not in near:
                    near.add(n)
                    nxt.append(n)
        frontier = nxt
    dist, prev = {c: 0.0 for c in piece}, {}
    heap = [(0.0, c) for c in piece]
    while heap:
        d, x = heapq.heappop(heap)
        if d > dist[x]:
            continue
        if x in sea:
            out = set()
            x = prev.get(x)
            while x is not None and x not in piece:
                out.add(x)
                x = prev.get(x)
            return out
        for n in grid.neighbours(x):
            if n in near:
                nd = d + (1.05 - min(1.0, share[n]))
                if nd < dist.get(n, 1e18):
                    dist[n], prev[n] = nd, x
                    heapq.heappush(heap, (nd, n))
    return set()


def join_components(grid, cand: set, marked: set, share: list) -> set:
    """`marked` plus the cheapest links (cost 1.05 − share per hex, through `cand`) joining its connected pieces."""
    import heapq

    out = set(marked)

    def comps(cells):
        seen, res = set(), []
        for c in cells:
            if c in seen:
                continue
            comp, stack = set(), [c]
            seen.add(c)
            while stack:
                x = stack.pop()
                comp.add(x)
                for n in grid.neighbours(x):
                    if n in cells and n not in seen:
                        seen.add(n)
                        stack.append(n)
            res.append(comp)
        return res

    isolated = set()  # cells of pieces that no path through `cand` links to any other piece
    while True:
        cs = [c for c in comps(out) if not c <= isolated]
        if len(cs) <= 1:
            return out
        cs.sort(key=len, reverse=True)
        main = cs[0]
        dist = {c: 0.0 for c in main}
        prev = {}
        heap = [(0.0, c) for c in main]
        hit = None
        while heap:
            d, x = heapq.heappop(heap)
            if d > dist.get(x, 1e18):
                continue
            if x in out and x not in main:
                hit = x
                break
            for n in grid.neighbours(x):
                if n not in cand:
                    continue
                nd = d + (1.05 - min(1.0, share[n]))
                if nd < dist.get(n, 1e18):
                    dist[n] = nd
                    prev[n] = x
                    heapq.heappush(heap, (nd, n))
        if hit is None:  # this piece is cut off from the others through `cand`: leave it as it is
            isolated |= main
            continue
        x = hit
        while x in prev:
            out.add(x)
            x = prev[x]


def classify_relief(mean: float, std: float) -> int:
    if mean >= PEAKS_MEAN:
        return PEAKS
    if std >= MOUNTAINS_STD or mean >= MOUNTAINS_MEAN:
        return MOUNTAINS
    if std >= HILLS_STD:
        return HILLS
    return FLAT


def clip_polyline(pts, width, height):
    """Runs of a polyline that stay inside the map rectangle."""
    runs, cur = [], []
    for x, y in pts:
        if 0 <= x <= width and 0 <= y <= height:
            cur.append((x, y))
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return [r for r in runs if len(r) >= 2]


def simplify(pts, tol):
    """Radial-distance thinning (keeps the ends)."""
    out = [pts[0]]
    for p in pts[1:-1]:
        if math.dist(p, out[-1]) >= tol:
            out.append(p)
    out.append(pts[-1])
    return out


def build() -> None:
    sb = load_interim("statcan_boundaries")
    ne = load_interim("natural_earth")
    et = load_interim("etopo")

    # --- projection and map frame ------------------------------------------------------------------------------
    probe = MapProjection(0.0, 0.0, 0.0)
    km = probe.km
    csd = sb["csd"]
    csd_km = [[[[km(lon, lat) for lon, lat in ring] for ring in poly] for poly in c["polys"]] for c in csd]
    xs = [x for c in csd_km for poly in c for x, _ in poly[0]]
    ys = [y for c in csd_km for poly in c for _, y in poly[0]]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    proj = MapProjection(round(min_x, 3), round(max_y, 3), MARGIN_UNITS)
    width = (max_x - min_x) * SCALE + 2 * MARGIN_UNITS
    height = (max_y - min_y) * SCALE + 2 * MARGIN_UNITS
    grid = HexGrid.covering(width, height, HEX_RADIUS_UNITS)
    print(f"    Québec {max_x - min_x:.0f} × {max_y - min_y:.0f} km; grid {grid.cols} × {grid.rows} = {grid.size} hexes")

    margin_km = MARGIN_UNITS / SCALE
    gx0, gy0 = min_x - margin_km, max_y + margin_km  # km of the map's top-left corner
    rw = math.ceil((grid.cols + 1) * math.sqrt(3) * HEX_RADIUS_UNITS / SCALE / RASTER_KM) + 2
    rh = math.ceil((grid.rows + 1) * 1.5 * HEX_RADIUS_UNITS / SCALE / RASTER_KM) + 2
    gx0 -= RASTER_KM * 2
    gy0 += RASTER_KM * 2

    def to_units(x, y):  # projected km → map units
        return (x - min_x) * SCALE + MARGIN_UNITS, (max_y - y) * SCALE + MARGIN_UNITS

    def to_km(ux, uy):
        return (ux - MARGIN_UNITS) / SCALE + min_x, max_y - (uy - MARGIN_UNITS) / SCALE

    # --- rasters --------------------------------------------------------------------------------------------------
    land = Raster(gx0, gy0, RASTER_KM, rw, rh)  # >= 0 SDR index, -2 neighbour, -1 water
    for nb in sb["neighbours"]:
        for poly in nb["polys"]:
            land.fill_polygon([[km(lon, lat) for lon, lat in ring] for ring in poly], FOREIGN)
    for c in ne["countries"]:
        for poly in c["polys"]:
            land.fill_polygon([[km(lon, lat) for lon, lat in ring] for ring in poly], FOREIGN)
    for k, polys in enumerate(csd_km):
        for poly in polys:
            land.fill_polygon(poly, k)
    lakes = Raster(gx0, gy0, RASTER_KM, rw, rh, fill=0, typecode="b")
    for lk in ne["lakes"]:
        for poly in lk["polys"]:
            lakes.fill_polygon([[km(lon, lat) for lon, lat in ring] for ring in poly], 1)
    # Atlas water bodies (1:1M): inland water the census polygons keep inside municipalities. The St. Lawrence is
    # marked apart (WB_RIVER) so that it stays joined to the estuary (sea/coast), the others count as lakes.
    wb = load_interim("atlas_water")
    wbr = Raster(gx0, gy0, RASTER_KM, rw, rh, fill=0, typecode="b")
    for body in wb["waterbodies"]:
        val = WB_RIVER if body["name"] in SEA_RIVERS else WB_LAKE
        wbr.fill_polygon([[km(lon, lat) for lon, lat in ring] for ring in body["rings"]], val)
    for isl in wb["islands"]:  # the water bodies keep no holes for their islands
        wbr.fill_polygon([[km(lon, lat) for lon, lat in ring] for ring in isl["rings"]], 0)
    wbd = wbr.data
    river_bodies = []  # indices into wb["waterbodies"] of the river-like bodies
    river_big = []  # …and whether each is big enough to be drawn along its whole course
    rvr = Raster(gx0, gy0, RASTER_KM, rw, rh, fill=-1, typecode="h")
    for k, body in enumerate(wb["waterbodies"]):
        rings = [[km(lon, lat) for lon, lat in ring] for ring in body["rings"]]
        area = is_river_like(rings)
        if area:
            rvr.fill_polygon(rings, len(river_bodies))
            river_bodies.append(k)
            river_big.append(area >= RIVER_COURSE_KM2)
    rvd = rvr.data
    er_codes = [e["uid"] for e in sb["er"]]
    er_r = Raster(gx0, gy0, RASTER_KM, rw, rh, fill=-1, typecode="b")
    for k, e in enumerate(sb["er"]):
        for poly in e["polys"]:
            er_r.fill_polygon([[km(lon, lat) for lon, lat in ring] for ring in poly], k)
    print(f"    rasters {rw} × {rh} at {RASTER_KM} km")

    # SDR → RÉ: the region under most of the SDR's pixels (regions are made of whole census divisions).
    er_votes = [Counter() for _ in csd]
    ld, ed = land.data, er_r.data
    for i in range(0, len(ld), 3):  # every third pixel is plenty for a majority vote
        k = ld[i]
        if k >= 0 and ed[i] >= 0:
            er_votes[k][ed[i]] += 1
    cd_votes = defaultdict(Counter)
    for k, c in enumerate(csd):
        if er_votes[k]:
            cd_votes[c["uid"][:4]][er_votes[k].most_common(1)[0][0]] += sum(er_votes[k].values())
    cd_er = {cd: v.most_common(1)[0][0] for cd, v in cd_votes.items()}

    # --- regions ("states") and census divisions ("counties") ------------------------------------------------------
    order = sorted(REGIONS, key=lambda u: REGIONS[u][0])
    state_of_er = {er_codes.index(u): s for s, u in enumerate(order)}
    states = [{"fips": u, "abbr": REGIONS[u][0], "name": REGIONS[u][1], "region": "Québec"} for u in order]
    cds = sb["cd"]
    cd_index = {c["uid"]: k for k, c in enumerate(cds)}
    missing = [c["uid"] for c in cds if c["uid"] not in cd_er]
    if missing:
        raise ValueError(f"DR sans région : {missing}")
    csd_state = []
    for c in csd:
        cd = c["uid"][:4]
        csd_state.append(state_of_er[cd_er[cd]])

    # --- sampling every hex ---------------------------------------------------------------------------------------
    offs = hex_offsets(HEX_RADIUS_UNITS / SCALE, SAMPLE_KM)
    ns = len(offs)
    owner = [WATER_CELL] * grid.size
    county = [-1] * grid.size
    land_samples = [0] * grid.size
    lake_share = [0.0] * grid.size
    water_share = [0.0] * grid.size  # share of the hex's sample points on water (outside land, or in an Atlas water body)
    river_cells = defaultdict(set)  # river-like body → hexes with a sample point in it
    csd_cells = defaultdict(list)  # csd index → [[cell, count, sum_ux, sum_uy]]
    best_for_csd: dict[int, tuple[int, int]] = {}
    wpx = land.w
    for i in range(grid.size):
        ux, uy = grid.center(*grid.col_row(i))
        cx, cy = to_km(ux, uy)
        counts = Counter()
        sums = defaultdict(lambda: [0.0, 0.0])
        n_foreign = n_water = n_lake = 0
        centre_val = None
        for dx, dy in offs:
            x, y = cx + dx, cy + dy
            c, r = int((x - gx0) // RASTER_KM), int((gy0 - y) // RASTER_KM)
            inside = 0 <= c < wpx and 0 <= r < land.h
            v = ld[r * wpx + c] if inside else WATER_CELL
            wv = wbd[r * wpx + c] if inside else 0
            if wv and v != WATER_CELL:  # land polygon, but under an Atlas water body: water
                v = WATER_CELL
            if centre_val is None:
                centre_val = v
            if v >= 0:
                counts[v] += 1
                s = sums[v]
                s[0] += ux + dx * SCALE
                s[1] += uy - dy * SCALE
            elif v == FOREIGN:
                n_foreign += 1
            else:
                n_water += 1
                if wv == WB_LAKE or (inside and lakes.data[r * wpx + c]):
                    n_lake += 1
        n_qc = sum(counts.values())
        land_samples[i] = n_qc
        lake_share[i] = n_lake / n_water if n_water else 0.0
        water_share[i] = n_water / ns
        for k, n in counts.items():
            csd_cells[k].append([i, n, sums[k][0], sums[k][1]])
            if n > best_for_csd.get(k, (-1, 0))[1]:
                best_for_csd[k] = (i, n)
        cats = {"qc": n_qc, "foreign": n_foreign, "water": n_water}
        top = max(cats.values())
        winners = [k for k, v in cats.items() if v == top]
        if len(winners) > 1:
            cat = "qc" if centre_val is not None and centre_val >= 0 else "foreign" if centre_val == FOREIGN else "water"
            cat = cat if cat in winners else winners[0]
        else:
            cat = winners[0]
        if cat == "qc":
            k = centre_val if centre_val is not None and centre_val >= 0 else counts.most_common(1)[0][0]
            owner[i] = csd_state[k]
            county[i] = cd_index[csd[k]["uid"][:4]]
        elif cat == "foreign":
            owner[i] = FOREIGN

    # Hexes touched by each river-like body: every raster pixel (500 m) of it, so a stretch narrower than the 1 km
    # sample lattice still links its hexes.
    for r in range(rvr.h):
        row = rvd[r * wpx:(r + 1) * wpx]
        if max(row) < 0:
            continue
        ky = gy0 - (r + 0.5) * RASTER_KM
        for c, b in enumerate(row):
            if b >= 0:
                cell = grid.cell_at(*to_units(gx0 + (c + 0.5) * RASTER_KM, ky))
                if cell >= 0:
                    river_cells[b].add(cell)
    # Major rivers narrower than a hex (see RIVER_* above): along each river-like Atlas water body, hexes with at least
    # RIVER_MIN_WATER of water become water, then the pieces are joined through the body's other hexes (the
    # wettest way), so the river reads as one chain of water hexes from end to end.
    river_hex = 0
    for b, cells in river_cells.items():
        cand = set(cells)
        marked = {c for c in cand if owner[c] == WATER_CELL or water_share[c] >= RIVER_MIN_WATER}
        if river_big[b]:  # a long river: also its whole course, end to end
            marked |= course(grid, cand, water_share)
        for c in join_components(grid, cand, marked, water_share):
            if owner[c] != WATER_CELL:
                owner[c] = WATER_CELL
                county[c] = -1
                river_hex += 1
    # The Atlas cuts one river into several bodies (at a named lake, a rapid, an island): join the pieces of the
    # whole network the same way, through hexes touched by these bodies only, so unrelated waters stay apart.
    network = set().union(*river_cells.values()) if river_cells else set()
    joined = join_components(grid, network, {c for c in network if owner[c] == WATER_CELL}, water_share)
    for c in joined:
        if owner[c] != WATER_CELL:
            owner[c] = WATER_CELL
            county[c] = -1
            river_hex += 1
    # …and a long network to the sea when it stops a few hexes short of it: at Québec the river is 1 to 2 km wide,
    # thinner than the sample lattice, and the Atlas hands over to the census coastline.
    sea_cells = set()  # water joined to the open sea at the edge of the map
    for i in range(grid.size):
        col, row = grid.col_row(i)
        if owner[i] == WATER_CELL and lake_share[i] < 0.5 and (col in (0, grid.cols - 1) or row in (0, grid.rows - 1)):
            sea_cells.add(i)
    sq = deque(sea_cells)
    while sq:
        for j in grid.neighbours(sq.popleft()):
            if j not in sea_cells and owner[j] == WATER_CELL and j not in network:
                sea_cells.add(j)
                sq.append(j)
    inland = {i for i in range(grid.size) if owner[i] == WATER_CELL and i not in sea_cells}
    for piece in components(grid, inland):
        if len(piece & network) >= SEA_LINK_MIN_HEXES:
            for c in link_to_sea(grid, piece, sea_cells, water_share, SEA_LINK_STEPS):
                network.add(c)
                if owner[c] != WATER_CELL:
                    owner[c] = WATER_CELL
                    county[c] = -1
                    river_hex += 1
    river_set = {c for c in network if owner[c] == WATER_CELL}

    # Every SDR with land gets at least one hex of Québec land: its best one, if none of its hexes is Québec land
    # (an island, or a strip of shore whose hexes all went to the water or to a neighbour).
    # An island SDR whose only hexes carry the river (Sorel islands, L'Île-Dorval…) keeps no hex: the river stays
    # unbroken and its residents go to the nearest Québec hex (see places.py).
    forced = 0
    for k, (cell, _) in best_for_csd.items():
        if cell in river_set:
            continue
        if all(owner[c[0]] < 0 for c in csd_cells[k]):
            owner[cell] = csd_state[k]
            county[cell] = cd_index[csd[k]["uid"][:4]]
            forced += 1
    csd_point = {}
    for k, c in enumerate(csd):
        if k in csd_cells:
            continue
        # no sample landed in it (tiny SDR): its largest ring's vertex mean
        ring = max((poly[0] for poly in csd_km[k]), key=len)
        x, y = sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)
        csd_point[k] = to_units(x, y)
    print(f"    {len(river_bodies)} river-like water bodies ({sum(river_big)} drawn end to end); "
          f"{river_hex} hexes turned to water along them")
    print(f"    {len(offs)} samples per hex; {forced} hexes given to an SDR with no majority; "
          f"{len(csd_point)} SDR too small for any sample point")

    # --- elevation and relief -------------------------------------------------------------------------------------
    stats_land = [[0, 0.0, 0.0, -10**9] for _ in range(grid.size)]  # n, sum, sumsq, max
    stats_all = [[0, 0.0, 0.0, -10**9] for _ in range(grid.size)]
    for lat, lon, alt in zip(et["lat"], et["lon"], et["alt"]):
        ux, uy = proj(lon, lat)
        i = grid.cell_at(ux, uy)
        if i < 0:
            continue
        for st, ok in ((stats_all[i], True), (stats_land[i], alt >= LAND_MIN_ALT_M)):
            if ok:
                st[0] += 1
                st[1] += alt
                st[2] += alt * alt
                st[3] = max(st[3], alt)

    def mean_std(st):
        n, s, ss, _ = st
        if not n:
            return None, 0.0
        m = s / n
        return m, math.sqrt(max(0.0, ss / n - m * m))

    elev = [0] * grid.size
    elev_max = [0] * grid.size
    relief = [FLAT] * grid.size
    no_elev = 0
    for i in range(grid.size):
        if owner[i] != WATER_CELL:
            m, sd = mean_std(stats_land[i])
            mx = stats_land[i][3]
            if m is None:
                m, sd = mean_std(stats_all[i])
                mx = stats_all[i][3]
            if m is None:
                no_elev += 1
                m, sd, mx = 0.0, 0.0, 0
            elev[i] = int(round(max(m, 0.0)))
            elev_max[i] = int(max(mx, 0))
            relief[i] = classify_relief(max(m, 0.0), sd)
        else:
            m, _ = mean_std(stats_all[i])
            elev[i] = int(round(min(m, 0.0))) if m is not None else -4000
    # --- water classes --------------------------------------------------------------------------------------------
    water = [LAND] * grid.size
    is_water = [o == WATER_CELL for o in owner]
    sea = [False] * grid.size
    q = deque()
    for i in range(grid.size):
        col, row = grid.col_row(i)
        if is_water[i] and (col in (0, grid.cols - 1) or row in (0, grid.rows - 1)) and lake_share[i] < 0.5:
            sea[i] = True
            q.append(i)
    while q:
        i = q.popleft()
        for j in grid.neighbours(i):
            if is_water[j] and not sea[j] and lake_share[j] < 0.5:
                sea[j] = True
                q.append(j)
    for i in range(grid.size):
        if not is_water[i]:
            continue
        if not sea[i]:
            water[i] = LAKE
            elev[i] = min(elev[i], 0) if elev[i] > -4000 else 0
            continue
        near_land = any(not is_water[j] for j in grid.neighbours(i))
        water[i] = COAST if near_land or elev[i] > COAST_DEPTH_M else OCEAN

    # --- rivers ---------------------------------------------------------------------------------------------------
    rivers = []
    for r in ne["rivers"]:
        if r["rank"] is None or r["rank"] > RIVER_MAX_RANK:
            continue
        for line in r["lines"]:
            pts = [proj(lon, lat) for lon, lat in line]
            for run in clip_polyline(pts, width, height):
                run = simplify(run, 4.0)
                if len(run) >= 2:
                    rivers.append({"name": r["name"] or "", "rank": int(r["rank"]),
                                   "pts": [round(v, 1) for p in run for v in p]})

    features = []
    for name, kind, lon, lat, fkm, ang in GEO_LABELS:
        x, y = proj(lon, lat)
        cell = grid.cell_at(x, y)
        if cell < 0 or not is_water[cell]:
            print(f"    ! étiquette « {name} » hors de l'eau ; ignorée")
            continue
        features.append({"name": name, "kind": kind, "x": round(x, 1), "y": round(y, 1),
                         "size": round(fkm * SCALE, 1), "angle": ang})

    n_qc = sum(1 for o in owner if o >= 0)
    print(f"    {n_qc} hexes in Québec, {sum(1 for o in owner if o == FOREIGN)} neighbour land, "
          f"{sum(1 for w in water if w)} water ({sum(1 for w in water if w == LAKE)} lake); {no_elev} without elevation; "
          f"{len(rivers)} river pieces")
    write_web("world.json", {
        "version": 2,
        "grid": grid.to_dict(),
        "width": round(width, 1),
        "height": round(height, 1),
        "margin": MARGIN_UNITS,
        "km_per_unit": round(1 / SCALE, 6),
        "insets": [],
        "owner": owner,
        "county": county,
        "elev": elev,
        "elev_max": elev_max,
        "water": water,
        "relief": relief,
        "cover": [0] * grid.size,
        "pct": None,
        "tables": {"water": WATER_TABLE, "relief": RELIEF_TABLE, "cover": COVER_TABLE,
                   "notes": {"water": WATER_NOTE, "relief": RELIEF_NOTE, "cover": COVER_NOTE}},
        "states": states,
        "counties": [{"geoid": c["uid"], "name": c["name"]} for c in cds],
        "rivers": rivers,
        "features": features,
    })
    save_interim("_world", {
        "grid": grid.to_dict(),
        "projection": proj.to_dict(),
        "owner": owner,
        "county": county,
        "water": water,
        "states": [s["fips"] for s in states],
        "counties": [c["uid"] for c in cds],
        "county_state": [state_of_er[cd_er[c["uid"]]] for c in cds],
        "csd": [c["uid"] for c in csd],
        "csd_name": [c["name"] for c in csd],
        "csd_type": [c["type"] for c in csd],
        "csd_land_km2": [c["land_km2"] for c in csd],
        "csd_state": csd_state,
        "csd_cells": {str(k): v for k, v in csd_cells.items()},
        "csd_point": {str(k): v for k, v in csd_point.items()},
        "land_samples": land_samples,
        "samples_per_cell": ns,
    })
