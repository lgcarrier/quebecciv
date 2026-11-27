"""Chiffres de population et des logements du Recensement de 2021 (Statistique Canada) :

* tableau 98-10-0002-01 : Canada, provinces et subdivisions de recensement (municipalités), population 2021 et 2016,
  superficie des terres ;
* tableau 98-10-0003-01 : régions métropolitaines de recensement (RMR) et agglomérations de recensement (AR), avec
  la liste de leurs subdivisions.

Les deux sont des CSV officiels (version française, séparateur « ; ») de la Base de données des tableaux de Statistique Canada (www150.statcan.gc.ca)."""

from __future__ import annotations

import csv
import io
import zipfile

from ..core.quebec import PRUID
from ..core.source import Source, SourceInfo

TABLES = {"98100002": "98-10-0002-01", "98100003": "98-10-0003-01"}


def _url(pid: str) -> str:
    return f"https://www150.statcan.gc.ca/n1/tbl/csv/{pid}-fra.zip"


def _rows(path, pid):
    with zipfile.ZipFile(path) as z:
        with z.open(f"{pid}.csv") as f:
            return [r for r in csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig"), delimiter=";") if len(r) > 5]


def _int(v: str):
    return int(v) if v and v.strip().lstrip("-").isdigit() else None


def _float(v: str):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class StatcanPopulation(Source):
    info = SourceInfo(
        id="statcan_population",
        title="Chiffres de population et des logements, Recensement de 2021",
        publisher="Statistique Canada",
        homepage="https://www150.statcan.gc.ca/t1/tbl1/fr/tv.action?pid=9810000201",
        license="Licence du gouvernement ouvert – Canada",
        description="Population au Recensement de 2021 et de 2016 de chacune des 1 282 subdivisions de recensement "
        "du Québec (tableau 98-10-0002-01) et composition des régions métropolitaines et agglomérations de "
        "recensement (tableau 98-10-0003-01). Huit subdivisions (des réserves et établissements autochtones) n'ont "
        "pas de chiffre publié (« .. » dans le tableau) : elles restent sans population sur la carte et ne sont pas "
        "comptées dans le total officiel du Québec.",
        used_for=["Population des municipalités", "Densité", "Croissance 2016-2021", "Villes (RMR et AR)",
                  "Population des régions et du Québec"],
    )

    def fetch(self, force=False):
        for pid in TABLES:
            self.download(_url(pid), f"{pid}-fra.zip", force=force, expect_binary=True)

    def process(self):
        # 98-10-0002-01 : les colonnes sont fixes (population 2021, 2016, superficie) ; le DGUID donne le niveau.
        rows = _rows(self.raw_dir / "98100002-fra.zip", "98100002")
        head = rows[0]
        i21, i16 = 4, 6
        iarea = next(k for k, h in enumerate(head) if "uperficie" in h)
        province, csd = None, {}
        for r in rows[1:]:
            dguid = r[2]
            if dguid == f"2021A0002{PRUID}":
                province = {"name": r[1], "pop2021": _int(r[i21]), "pop2016": _int(r[i16]),
                            "land_km2": _float(r[iarea])}
            elif dguid.startswith(f"2021A0005{PRUID}"):
                csd[dguid[9:]] = {"name": r[1], "pop2021": _int(r[i21]), "pop2016": _int(r[i16]),
                                  "status2021": r[i21 + 1] or None, "land_km2": _float(r[iarea])}
        if province is None or not csd:
            raise ValueError("98-10-0002-01 : ligne du Québec ou SDR introuvables")
        # 98-10-0003-01 : chaque RMR/AR (DGUID 2021S0503… RMR, 2021S0504… AR) suivie de ses SDR (2021A0005…).
        cmas, cur = {}, None
        for r in _rows(self.raw_dir / "98100003-fra.zip", "98100003")[1:]:
            d = r[2]
            if d.startswith(("2021S0503", "2021S0504")):
                cur = d[9:]
                cmas[cur] = {"uid": cur, "kind": "RMR" if d.startswith("2021S0503") else "AR", "name": r[1],
                             "pop2021": _int(r[4]), "pop2016": _int(r[6]), "members": []}
            elif d.startswith("2021A0005") and cur:
                cmas[cur]["members"].append(d[9:])
        qc = {k: v for k, v in cmas.items() if any(m.startswith(PRUID) for m in v["members"])}
        return {
            "vintage": "Recensement de 2021 (tableaux 98-10-0002-01 et 98-10-0003-01)",
            "_files": [f"{pid}-fra.zip" for pid in TABLES],
            "province": province,
            "csd": csd,
            "cma": qc,
        }
