"""Atlas du Canada, données à l'échelle nationale 1:1 000 000 : étendues d'eau (RNCan).

Les limites cartographiques de Statistique Canada ne retirent que les grandes eaux (mer, estuaire, grands lacs) : le
Saint-Laurent fluvial, le lac Saint-Pierre, l'Outaouais ou le Saguenay y restent à l'intérieur des municipalités.
Ces polygones d'étendues d'eau permanentes disent où est l'eau. Le fichier de formes (shapefile) est lu ici avec la
bibliothèque standard (zipfile + struct), et sa projection conique conforme de Lambert (NAD83, « Canada Atlas
Lambert ») est inversée en longitude/latitude (formules de Snyder, ellipsoïde GRS 1980)."""

from __future__ import annotations

import math
import struct
import zipfile

from ..core.quebec import BBOX
from ..core.source import Source, SourceInfo

URL = ("https://ftp.geogratis.gc.ca/pub/nrcan_rncan/vector/framework_cadre/Atlas_of_Canada_1M/hydrology/"
       "AC_1M_Waterbodies.shp.zip")
STEM = "AC_1M_Waterbodies_shp/AC_1M_Waterbodies"
# The water bodies have no holes for their islands: the Atlas keeps islands in their own layer (Île de Montréal,
# Île Jésus, Île d'Orléans…), which the map subtracts from the water.
ISLANDS_URL = "https://ftp.geogratis.gc.ca/pub/nrcan_rncan/vector/framework_cadre/Atlas_of_Canada_1M/coasts/AC_1M_Islands.shp.zip"
ISLANDS_STEM = "AC_1M_Islands_shp/AC_1M_Islands"
SIMPLIFY_M = 150.0  # vertices closer than this to the last kept one are dropped (the map raster is 500 m)


class LambertConformalConic:
    """NAD83 Canada Atlas Lambert (EPSG:3978): GRS 1980, standard parallels 49° and 77°, origin 49° N 95° W."""

    def __init__(self, lat1=49.0, lat2=77.0, lat0=49.0, lon0=-95.0, a=6378137.0, inv_f=298.257222101):
        f = 1 / inv_f
        self.e = e = math.sqrt(2 * f - f * f)
        self.a, self.lon0 = a, math.radians(lon0)
        p1, p2, p0 = (math.radians(v) for v in (lat1, lat2, lat0))
        m1, m2 = self._m(p1), self._m(p2)
        t1, t2, t0 = self._t(p1), self._t(p2), self._t(p0)
        self.n = (math.log(m1) - math.log(m2)) / (math.log(t1) - math.log(t2))
        self.F = m1 / (self.n * t1 ** self.n)
        self.rho0 = a * self.F * t0 ** self.n
        del e

    def _m(self, p):
        return math.cos(p) / math.sqrt(1 - (self.e * math.sin(p)) ** 2)

    def _t(self, p):
        es = self.e * math.sin(p)
        return math.tan(math.pi / 4 - p / 2) / ((1 - es) / (1 + es)) ** (self.e / 2)

    def forward(self, lon, lat):
        p = math.radians(lat)
        rho = self.a * self.F * self._t(p) ** self.n
        th = self.n * (math.radians(lon) - self.lon0)
        return rho * math.sin(th), self.rho0 - rho * math.cos(th)

    def inverse(self, x, y):
        dy = self.rho0 - y
        rho = math.copysign(math.hypot(x, dy), self.n)
        t = (rho / (self.a * self.F)) ** (1 / self.n)
        th = math.atan2(x, dy)
        lon = th / self.n + self.lon0
        p = math.pi / 2 - 2 * math.atan(t)
        for _ in range(8):
            es = self.e * math.sin(p)
            p = math.pi / 2 - 2 * math.atan(t * ((1 - es) / (1 + es)) ** (self.e / 2))
        return math.degrees(lon), math.degrees(p)


def _text(b: bytes) -> str:
    try:
        return b.decode("utf-8").strip()
    except UnicodeDecodeError:
        return b.decode("latin-1").strip()


def read_dbf(data: bytes) -> list[dict]:
    n, hl, rl = struct.unpack("<IHH", data[4:12])
    fields, off = [], 1
    for i in range(32, hl - 1, 32):
        f = data[i:i + 32]
        fields.append((f[:11].split(b"\0")[0].decode("ascii"), off, f[16]))
        off += f[16]
    rows = []
    for k in range(n):
        b = data[hl + k * rl: hl + (k + 1) * rl]
        rows.append({name: _text(b[o:o + ln]) for name, o, ln in fields})
    return rows


def read_shp_polygons(data: bytes):
    """Yield (bbox, rings) for each record of a polygon shapefile (type 5); rings in file coordinates."""
    pos = 100
    while pos < len(data):
        _, clen = struct.unpack(">II", data[pos:pos + 8])
        rec = data[pos + 8: pos + 8 + clen * 2]
        pos += 8 + clen * 2
        stype = struct.unpack("<i", rec[:4])[0]
        if stype == 0:
            yield None, []
            continue
        if stype != 5:
            raise ValueError(f"type de forme {stype} inattendu (polygone attendu)")
        bbox = struct.unpack("<4d", rec[4:36])
        nparts, npts = struct.unpack("<ii", rec[36:44])
        parts = list(struct.unpack(f"<{nparts}i", rec[44:44 + 4 * nparts])) + [npts]
        base = 44 + 4 * nparts
        coords = struct.unpack(f"<{2 * npts}d", rec[base: base + 16 * npts])
        rings = [[(coords[2 * k], coords[2 * k + 1]) for k in range(parts[j], parts[j + 1])] for j in range(nparts)]
        yield bbox, rings


def thin(ring, tol):
    out = [ring[0]]
    for p in ring[1:]:
        if abs(p[0] - out[-1][0]) + abs(p[1] - out[-1][1]) >= tol:
            out.append(p)
    return out if len(out) >= 4 else ring


class AtlasWater(Source):
    info = SourceInfo(
        id="atlas_water",
        title="Atlas du Canada 1:1 000 000 – Étendues d'eau",
        publisher="Ressources naturelles Canada",
        homepage="https://open.canada.ca/data/fr/dataset/e9931fc7-034c-52ad-91c5-6c64d4ba0065",  # îles : 863ad03d-4426-5334-83b7-db054b23df89
        license="Licence du gouvernement ouvert – Canada",
        description="Polygones des lacs, réservoirs et grands cours d'eau permanents du Canada à l'échelle de 1:1 000 000 "
        "(données nationales de l'Atlas du Canada), moins les îles de la couche « Îles » du même atlas. Ils marquent l'eau que les limites cartographiques de Statistique "
        "Canada laissent dans les municipalités : le Saint-Laurent fluvial, le lac Saint-Pierre, l'Outaouais, le "
        "Saguenay et les lacs de l'intérieur.",
        used_for=["Terre et eau (fleuve, rivières larges, lacs)"],
    )

    def fetch(self, force=False):
        self.download(URL, "AC_1M_Waterbodies.shp.zip", force=force, expect_binary=True)
        self.download(ISLANDS_URL, "AC_1M_Islands.shp.zip", force=force, expect_binary=True)

    def _read(self, zip_name, stem, keep=lambda row: True):
        lcc = LambertConformalConic()
        lon_min, lat_min, lon_max, lat_max = BBOX
        with zipfile.ZipFile(self.raw_dir / zip_name) as z:
            shp = z.read(stem + ".shp")
            rows = read_dbf(z.read(stem + ".dbf"))
        out = []
        for (bbox, rings), row in zip(read_shp_polygons(shp), rows):
            if bbox is None or not keep(row):
                continue
            corners = [lcc.inverse(x, y) for x in (bbox[0], bbox[2]) for y in (bbox[1], bbox[3])]
            # the four corners of a projected box bound its lon/lat box closely enough at this scale; pad by 0.5°
            if (max(c[0] for c in corners) < lon_min - 0.5 or min(c[0] for c in corners) > lon_max + 0.5
                    or max(c[1] for c in corners) < lat_min - 0.5 or min(c[1] for c in corners) > lat_max + 0.5):
                continue
            ll = []
            for ring in rings:
                ring = thin(ring, SIMPLIFY_M)
                ll.append([(round(lon, 4), round(lat, 4)) for lon, lat in (lcc.inverse(x, y) for x, y in ring)])
            out.append({"name": row.get("NOM") or row.get("NAME") or "", "rings": ll})
        return out

    def process(self):
        water = self._read("AC_1M_Waterbodies.shp.zip", STEM, lambda row: row.get("TYPE") == "Permanent Water")
        islands = self._read("AC_1M_Islands.shp.zip", ISLANDS_STEM)
        return {"vintage": "Atlas du Canada, données nationales 1:1 000 000 (version 2017)",
                "_files": ["AC_1M_Waterbodies.shp.zip", "AC_1M_Islands.shp.zip"],
                "waterbodies": water, "islands": islands}
