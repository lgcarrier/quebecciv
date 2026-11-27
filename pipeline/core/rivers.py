"""Rivers too narrow for the hexes, drawn at their true width (standard library only).

The St. Lawrence between Montréal and Québec is 1 to 3 km wide and the Saguenay fjord 1.5 to 3 km, against 8.7 km for
a hex: no hex along them is mostly water. Rather than turn land hexes into water (a river four times too wide, with the
people of its banks pushed off their own hexes), the map draws such a river as a ribbon on top of the land hexes:

* `route` finds the way through the water pixels of the builder's raster from a point upstream to the sea (or to a
  waypoint), keeping to the middle of the water;
* `cross_sections` measures the water across the route at each step, which gives the centre line and the true width;
* `land_runs` keeps the parts that cross land hexes (plus a short overlap into the water hexes at each end, so the ribbon
  joins the lakes and the estuary drawn as hexes);
* `simplify` and `smooth` thin and round the line for the browser.

Everything here works on pixel coordinates (column, row; floats once the centre line is refined) of a raster whose
water test is a callable, so it can be tested on a small hand-made grid.
"""

from __future__ import annotations

import heapq
import math

SQRT2 = math.sqrt(2)
NEIGHBOURS = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
              (1, 1, SQRT2), (1, -1, SQRT2), (-1, 1, SQRT2), (-1, -1, SQRT2)]
CLEARANCE_MAX = 6  # pixels: beyond this the water is "wide open" and the route no longer cares where it is
LAND_COST = 40.0  # a step over land costs this many steps of open water: only to cross a gap between two sources
MAX_EXPANSIONS = 4_000_000


def nearest_water(is_water, c: int, r: int, radius: int = 12) -> tuple[int, int] | None:
    """The water pixel nearest to (c, r) within `radius` pixels (rings of growing size), or None."""
    if is_water(c, r):
        return c, r
    for k in range(1, radius + 1):
        best = None
        for dc in range(-k, k + 1):
            for dr in ((-k, k) if abs(dc) < k else range(-k, k + 1)):
                if is_water(c + dc, r + dr):
                    d = dc * dc + dr * dr
                    if best is None or d < best[0]:
                        best = (d, c + dc, r + dr)
        if best:
            return best[1], best[2]
    return None


def route(is_water, start: tuple[int, int], goal, size: tuple[int, int] | None = None,
          land_cost: float = LAND_COST) -> list[tuple[int, int]] | None:
    """Cheapest 8-connected chain of pixels from `start` to the first pixel where `goal(c, r)` is true.

    A step through water costs its length, more near a shore (1 + 3 / clearance², the clearance being the distance in
    pixels to the nearest land, up to CLEARANCE_MAX), so the chain follows the middle of the water. A step over land
    costs `land_cost` times its length: the chain crosses land only where the water is cut (a river narrower than a
    pixel, or the seam between two data sources). `size` (columns, rows) keeps the chain inside the raster. None when
    the goal cannot be reached."""
    clearance_cache: dict[tuple[int, int], int] = {}

    def clearance(c, r):
        v = clearance_cache.get((c, r))
        if v is None:
            v = CLEARANCE_MAX
            for k in range(1, CLEARANCE_MAX):
                if any(not is_water(c + dc, r + dr)
                       for dc in range(-k, k + 1) for dr in ((-k, k) if abs(dc) < k else range(-k, k + 1))):
                    v = k
                    break
            clearance_cache[(c, r)] = v
        return v

    dist = {start: 0.0}
    prev: dict[tuple[int, int], tuple[int, int]] = {}
    heap = [(0.0, start)]
    n = 0
    while heap:
        d, p = heapq.heappop(heap)
        if d > dist[p]:
            continue
        if goal(*p):
            out = [p]
            while p in prev:
                p = prev[p]
                out.append(p)
            return out[::-1]
        n += 1
        if n > MAX_EXPANSIONS:
            return None
        c, r = p
        for dc, dr, ln in NEIGHBOURS:
            q = (c + dc, r + dr)
            if size and not (0 <= q[0] < size[0] and 0 <= q[1] < size[1]):
                continue
            step = ln * (1.0 + 3.0 / clearance(*q) ** 2) if is_water(*q) else ln * land_cost
            nd = d + step
            if nd < dist.get(q, 1e18):
                dist[q] = nd
                prev[q] = p
                heapq.heappush(heap, (nd, q))
    return None


def cross_sections(is_water, path: list, reach: float = 12.0, step: float = 0.25, span: int = 3):
    """For each pixel of `path`: the middle of the water across the route there, and its width, in pixels.

    The water is walked perpendicular to the route (direction taken `span` pixels before and after) in steps of
    `step` pixel, up to `reach` pixels on each side. Returns [(c, r, width)], with c and r now fractional (pixel
    centres are at integers). Where the route is on land the width is 0 and the point is left where it is."""
    out = []
    n = len(path)

    def wet(x, y):
        return is_water(int(math.floor(x + 0.5)), int(math.floor(y + 0.5)))

    for i, (c, r) in enumerate(path):
        a, b = path[max(0, i - span)], path[min(n - 1, i + span)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        dl = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / dl, dx / dl
        if not is_water(c, r):
            out.append((float(c), float(r), 0.0))
            continue
        sides = []
        for sgn in (1, -1):
            t = 0.0
            while t < reach and wet(c + sgn * nx * (t + step), r + sgn * ny * (t + step)):
                t += step
            sides.append(t)
        left, right = sides
        mid = (left - right) / 2
        out.append((c + nx * mid, r + ny * mid, left + right + step))
    return out


def running(values: list[float], half: int, how) -> list[float]:
    """`how` (e.g. statistics.median) of each value's window of ± `half` neighbours."""
    n = len(values)
    return [how(values[max(0, i - half): min(n, i + half + 1)]) for i in range(n)]


def land_runs(on_land: list[bool], overlap: int = 4, min_len: int = 3) -> list[tuple[int, int]]:
    """Index ranges [i0, i1) of the stretches of a route that cross land hexes, each carried on into the water hexes
    at its ends until `overlap` points in a row are over water (so the ribbon reaches into the lake or the sea it
    joins, and ends there). Stretches shorter than `min_len` points (the route clipping the corner of a land hex) do
    not start a range of their own; ranges that touch are merged."""
    n = len(on_land)

    def carry(k, step):
        """From the land point k, the last index reached going `step` (±1) once `overlap` water points have been
        passed in a row, or the end of the route."""
        wet = 0
        while 0 <= k + step < n and wet < overlap:
            k += step
            wet = 0 if on_land[k] else wet + 1
        return k

    runs, i = [], 0
    while i < n:
        if not on_land[i]:
            i += 1
            continue
        j = i
        while j < n and on_land[j]:
            j += 1
        if j - i >= min_len:
            runs.append((carry(i, -1), carry(j - 1, 1) + 1))
        i = j
    merged = []
    for a, b in runs:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return merged


def simplify(points: list[tuple[float, float]], tol: float) -> list[int]:
    """Douglas-Peucker: indices of the points to keep so that none of the others is farther than `tol` from the line."""
    if len(points) < 3:
        return list(range(len(points)))
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = points[a]
        bx, by = points[b]
        dx, dy = bx - ax, by - ay
        dl = math.hypot(dx, dy)
        worst, at = 0.0, -1
        for k in range(a + 1, b):
            px, py = points[k]
            d = abs(dx * (py - ay) - dy * (px - ax)) / dl if dl else math.hypot(px - ax, py - ay)
            if d > worst:
                worst, at = d, k
        if worst > tol:
            keep[at] = True
            stack += [(a, at), (at, b)]
    return [k for k, v in enumerate(keep) if v]


def smooth(points: list[tuple[float, float]], widths: list[float], passes: int = 1):
    """Chaikin corner cutting (the two ends stay where they are); the widths are interpolated the same way."""
    for _ in range(passes):
        if len(points) < 3:
            break
        np_, nw = [points[0]], [widths[0]]
        for k in range(len(points) - 1):
            (ax, ay), (bx, by) = points[k], points[k + 1]
            wa, wb = widths[k], widths[k + 1]
            np_ += [(0.75 * ax + 0.25 * bx, 0.75 * ay + 0.25 * by), (0.25 * ax + 0.75 * bx, 0.25 * ay + 0.75 * by)]
            nw += [0.75 * wa + 0.25 * wb, 0.25 * wa + 0.75 * wb]
        np_.append(points[-1])
        nw.append(widths[-1])
        points, widths = np_, nw
    return points, widths
