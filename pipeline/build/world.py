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
# Terre ou eau : un hexagone est de la terre quand au moins la moitié de ses points d'échantillonnage tombent sur
# la terre (une SDR du Québec ou un voisin), l'eau des étendues de l'Atlas du Canada retirée. Le Saint-Laurent
# fluvial (1 à 3 km de large) et le fjord du Saguenay sont plus étroits qu'un hexagone (8,7 km) : à la majorité, ils
# seraient coupés. On y creuse donc un chenal minimal : la suite d'hexagones qui relie l'amont à la mer en
# convertissant le moins de terre possible (les plus mouillés d'abord), sans jamais prendre l'hexagone de terre
# réservé à une municipalité (voir plus bas).
CHANNELS = [  # (nom, point d'amont lon/lat) ; l'aval est la mer reliée au bord de la carte
    ("Saint-Laurent (lac Saint-Louis → estuaire)", -73.85, 45.40),
    ("Saguenay (Chicoutimi → Tadoussac)", -71.06, 48.43),
]
WB_LAKE, WB_RIVER = 1, 2
# Atlas water bodies joined to the sea (not counted as lakes). Only two pieces carry this name, both upstream of
# Montréal (Cornwall to Lake Ontario): the river from Montréal to Québec is unnamed in the Atlas, which is why the
# channels and river_system() decide its class below.
SEA_RIVERS = {"Fleuve Saint-Laurent"}
RIVER_STEP_KM = 0.5

WATER_TABLE = [
    {"id": LAND, "name": "Terre", "rule": "Au moins la moitié des points d'échantillonnage de l'hexagone (67, "
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
              "au 1:1 000 000 : les limites de Statistique Canada les laissent dans les municipalités. Un hexagone est "
              "de la terre quand au moins la moitié de ses points tombent sur la terre. Chaque municipalité garde au "
              "moins un hexagone de terre : celui où elle a le plus de points, même s'il est surtout dans l'eau (une "
              "île). Le Saint-Laurent fluvial et le Saguenay, plus étroits qu'un hexagone, reçoivent un chenal minimal "
              "d'hexagones d'eau jusqu'à l'estuaire (les hexagones de terre les plus mouillés, jamais celui réservé à "
              "une municipalité) ; ils paraissent donc plus larges qu'en réalité par endroits.")
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


def channel(grid, start: int, targets: set, step_cost, blocked: set) -> list[int] | None:
    """Cheapest chain of hexes from `start` to any hex of `targets` (Dijkstra; `step_cost(cell)` to enter a hex),
    never through `blocked`. None when no chain exists."""
    import heapq

    dist, prev, heap = {start: 0.0}, {}, [(0.0, start)]
    while heap:
        d, x = heapq.heappop(heap)
        if d > dist[x]:
            continue
        if x in targets:
            out = [x]
            while x in prev:
                x = prev[x]
                out.append(x)
            return out[::-1]
        for n in grid.neighbours(x):
            if n in blocked:
                continue
            nd = d + step_cost(n)
            if nd < dist.get(n, 1e18):
                dist[n], prev[n] = nd, x
                heapq.heappush(heap, (nd, n))
    return None


def sea_flood(grid, is_water, lake_share, through=frozenset()) -> set:
    """Water hexes joined to the open sea: the water hexes on the edge of the map that are not lakes, and every water
    hex reached from them through hexes that are not lakes (`lake_share` < 0.5) or that belong to `through` (the river
    channels, which are sea whatever the Atlas calls the water under them)."""
    def open_water(i):
        return is_water[i] and (lake_share[i] < 0.5 or i in through)

    sea, q = set(), deque()
    for i in range(grid.size):
        col, row = grid.col_row(i)
        if (col in (0, grid.cols - 1) or row in (0, grid.rows - 1)) and open_water(i):
            sea.add(i)
            q.append(i)
    while q:
        for j in grid.neighbours(q.popleft()):
            if j not in sea and open_water(j):
                sea.add(j)
                q.append(j)
    return sea


def river_system(grid, is_water, lake_share, channel_cells) -> set:
    """The channels plus the lake-like water hexes joined to them through lake-like hexes: the widenings of the river
    (Lac Saint-Louis, Lac Saint-Pierre) and the reaches the Atlas leaves unnamed, which `lake_share` counts as lakes.
    They are one body of water with the channel, so they take its class."""
    out, q = set(channel_cells), deque(channel_cells)
    while q:
        for j in grid.neighbours(q.popleft()):
            if j not in out and is_water[j] and lake_share[j] >= 0.5:
                out.add(j)
                q.append(j)
    return out


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
        # Land when at least half of the points are land (Québec or a neighbour); then Québec or the neighbour,
        # whichever has more points (the centre breaks a tie).
        if 2 * (n_qc + n_foreign) < ns:
            cat = "water"
        elif n_qc != n_foreign:
            cat = "qc" if n_qc > n_foreign else "foreign"
        else:
            cat = "qc" if centre_val is not None and centre_val >= 0 else "foreign"
        if cat == "qc":
            k = centre_val if centre_val is not None and centre_val >= 0 else counts.most_common(1)[0][0]
            owner[i] = csd_state[k]
            county[i] = cd_index[csd[k]["uid"][:4]]
        elif cat == "foreign":
            owner[i] = FOREIGN

    # Every SDR keeps at least one hex of Québec land: if none of its hexes is land by the majority rule (an island,
    # a strip of shore), the hex where it has the most points becomes its land. The river channels below never take
    # the last land hex of an SDR.
    forced = 0
    for k, (cell, _) in sorted(best_for_csd.items(), key=lambda kv: len(csd_cells[kv[0]])):
        if all(owner[c[0]] < 0 for c in csd_cells[k]):
            owner[cell] = csd_state[k]
            county[cell] = cd_index[csd[k]["uid"][:4]]
            forced += 1
    # Minimal channels (see CHANNELS): from the upstream hex to the sea, converting the fewest and wettest land hexes.
    # The sea a channel must reach is the one the water classes use below (sea_flood): water joined to the edge of the
    # map without crossing a lake. Aiming at any water joined to the edge would let a channel stop in a lake.
    sea_cells = sea_flood(grid, [o == WATER_CELL for o in owner], lake_share)

    def step_cost(c):
        if owner[c] == WATER_CELL:
            return 0.01
        return 1.0 + (1.0 - water_share[c]) + (2.0 if owner[c] == FOREIGN else 0.0)

    river_hex = 0
    channel_report = []
    channel_cells = set()
    for name, lon, lat in CHANNELS:
        start = grid.cell_at(*proj(lon, lat))
        blocked = set()  # hexes an SDR cannot lose (its only land, or the last of its land along the channel)
        while True:
            only = set()
            for k, cells in csd_cells.items():
                lc = [c[0] for c in cells if owner[c[0]] >= 0]
                if len(lc) == 1:
                    only.add(lc[0])
            path = channel(grid, start, sea_cells, step_cost, (blocked | only) - {start})
            if path is None:
                raise ValueError(f"chenal impossible sans retirer à une municipalité sa dernière terre : {name}")
            conv = set(c for c in path if owner[c] != WATER_CELL)
            # An SDR whose land hexes are all on the path keeps the one where it has the most points: block it, retry.
            lost = [k for k, cells in csd_cells.items()
                    if any(owner[c[0]] >= 0 for c in cells) and all(owner[c[0]] < 0 or c[0] in conv for c in cells)]
            if not lost:
                break
            for k in lost:
                blocked.add(max((c for c in csd_cells[k] if c[0] in conv), key=lambda c: (c[1], -c[0]))[0])
        for c in conv:
            owner[c] = WATER_CELL
            county[c] = -1
        river_hex += len(conv)
        channel_cells |= set(path)
        sea_cells = sea_flood(grid, [o == WATER_CELL for o in owner], lake_share, channel_cells)
        channel_report.append(f"{name} {len(path)} hexes, {len(conv)} land hexes made water")

    csd_point = {}
    for k, c in enumerate(csd):
        if k in csd_cells:
            continue
        # no sample landed in it (tiny SDR): its largest ring's vertex mean
        ring = max((poly[0] for poly in csd_km[k]), key=len)
        x, y = sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)
        csd_point[k] = to_units(x, y)
        # …whose hex is land too, if it fell in the water (a small island or a shore village), unless it carries a
        # river channel.
        cell = grid.cell_at(*csd_point[k])
        if cell >= 0 and owner[cell] == WATER_CELL and cell not in channel_cells:
            owner[cell] = csd_state[k]
            county[cell] = cd_index[csd[k]["uid"][:4]]
            forced += 1
    print(f"    channels: {'; '.join(channel_report)}")
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
    # The channels and the river lakes joined to them are sea (class « Côte »), not lakes: the Atlas leaves the river
    # from Montréal to Québec and the Saguenay unnamed (see SEA_RIVERS), so by name alone they would be classed as
    # lakes, cut off from the estuary.
    sea = sea_flood(grid, is_water, lake_share, river_system(grid, is_water, lake_share, channel_cells))
    for i in range(grid.size):
        if not is_water[i]:
            continue
        if i not in sea:
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
