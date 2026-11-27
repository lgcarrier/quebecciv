"""`pipeline check` : valide les fichiers de web/data contre docs/DATA_CONTRACTS.md et affiche un petit rapport.

Niveaux : PASS, NOTE, WARN, FAIL (un FAIL fait échouer la commande). Les modules de pipeline/build peuvent définir
`check(web_dir: Path) -> list[(niveau, message)]` : ils sont découverts et exécutés à la fin.

Contrôle clé : la somme des populations des 1 282 subdivisions (communes.json) doit égaler exactement le total
officiel du Québec au Recensement de 2021 publié dans le même tableau (nation.json `population_official`)."""

from __future__ import annotations

import importlib
import json
import math
import pkgutil
import re
from pathlib import Path

from .core.paths import WEB, WEB_DATA

REQUIRED = ["world", "cities", "nation", "states", "lenses", "sources"]
OPTIONAL = ["communes", "projection", "placenames/top"]
N_REGIONS = 17
N_CSD = 1282


class Report:
    def __init__(self, quiet: bool = False):
        self.items: list[tuple[str, str]] = []
        self.quiet = quiet

    def _add(self, level, msg):
        self.items.append((level, msg))
        if not self.quiet:
            print(f"  {level:4} {msg}")

    def ok(self, msg): self._add("PASS", msg)
    def note(self, msg): self._add("NOTE", msg)
    def warn(self, msg): self._add("WARN", msg)
    def fail(self, msg): self._add("FAIL", msg)

    def section(self, title):
        if not self.quiet:
            print(f"\n[{title}]")

    def count(self, level):
        return sum(1 for lv, _ in self.items if lv == level)

    @property
    def failed(self):
        return self.count("FAIL") > 0


def _load(r: Report, web_dir: Path, name: str, required: bool):
    p = web_dir / f"{name}.json"
    if not p.exists():
        (r.fail if required else r.note)(f"{name}.json absent")
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        r.fail(f"{name}.json illisible : {e}")
        return None


def check_world(r: Report, w) -> dict | None:
    r.section("world.json")
    keys = ["grid", "width", "height", "km_per_unit", "owner", "county", "elev", "elev_max", "water", "relief",
            "cover", "tables", "states", "counties", "rivers"]
    missing = [k for k in keys if k not in w]
    if missing:
        r.fail(f"clés manquantes : {missing}")
        return None
    n = w["grid"]["cols"] * w["grid"]["rows"]
    for k in ("owner", "county", "elev", "elev_max", "water", "relief", "cover"):
        if len(w[k]) != n:
            r.fail(f"{k} : {len(w[k])} valeurs au lieu de {n}")
            return None
    ns, nc = len(w["states"]), len(w["counties"])
    if ns != N_REGIONS:
        r.fail(f"{ns} régions au lieu de {N_REGIONS}")
    bad = [i for i, o in enumerate(w["owner"]) if not (-2 <= o < ns)]
    if bad:
        r.fail(f"owner hors bornes dans {len(bad)} cellules")
    land = [i for i, o in enumerate(w["owner"]) if o >= 0]
    if any(not (0 <= w["county"][i] < nc) for i in land):
        r.fail("une cellule du Québec sans MRC (county)")
    if any(w["county"][i] != -1 for i, o in enumerate(w["owner"]) if o < 0):
        r.fail("county ≠ -1 hors du Québec")
    if any(w["water"][i] != 0 for i in land) or any(w["water"][i] == 0 for i, o in enumerate(w["owner"]) if o == -1):
        r.fail("water incohérent avec owner")
    seen = {w["owner"][i] for i in land}
    if len(seen) != ns:
        r.fail(f"{ns - len(seen)} région(s) sans hexagone")
    r.ok(f"grille {w['grid']['cols']} × {w['grid']['rows']} = {n} hexagones de {w['grid']['radius'] * w['km_per_unit']:.1f} km "
         f"de rayon ; {len(land)} au Québec, {sum(1 for o in w['owner'] if o == -2)} chez les voisins")
    r.ok(f"{ns} régions, {nc} divisions de recensement (MRC et équivalents), {len(w['rivers'])} tronçons de rivière")
    return {"n": n, "owner": w["owner"], "states": w["states"]}


def check_cities(r: Report, cities, ctx):
    r.section("cities.json")
    if not isinstance(cities, list) or not cities:
        return r.fail("liste de villes vide")
    keys = ["id", "name", "full", "states", "x", "y", "cell", "population", "capital", "footprint", "ranks", "peers"]
    for c in cities:
        miss = [k for k in keys if k not in c]
        if miss:
            return r.fail(f"{c.get('id')} : clés manquantes {miss}")
    ids = [c["id"] for c in cities]
    if len(set(ids)) != len(ids):
        r.fail("identifiants de ville en double")
    if any(cities[k]["population"] < cities[k + 1]["population"] for k in range(len(cities) - 1)):
        r.fail("villes non triées par population décroissante")
    if ctx:
        off = [c["id"] for c in cities if not (0 <= c["cell"] < ctx["n"]) or ctx["owner"][c["cell"]] < 0]
        if off:
            r.fail(f"villes hors du Québec : {off}")
        cells = [c["cell"] for c in cities]
        if len(set(cells)) != len(cells):
            r.warn("deux villes partagent un hexagone")
    caps = [c["name"] for c in cities if c["capital"]]
    if caps != ["Québec"]:
        r.fail(f"capitale attendue : Québec, trouvé {caps}")
    if any(c.get("yields") not in (None, {}) for c in cities):
        r.fail("des rendements (yields) sont présents sans source documentée")
    r.ok(f"{len(cities)} villes ({sum(1 for c in cities if c.get('kind') in ('RMR', 'AR'))} RMR/AR), "
         f"la plus grande : {cities[0]['name']} ({cities[0]['population']:,} hab.)")


def check_states(r: Report, states, ctx):
    r.section("states.json")
    if len(states) != N_REGIONS:
        return r.fail(f"{len(states)} régions au lieu de {N_REGIONS}")
    if ctx and [s["fips"] for s in states] != [s["fips"] for s in ctx["states"]]:
        r.fail("ordre des régions différent de world.json")
    abbr = [s["abbr"] for s in states]
    if abbr != [f"{k:02d}" for k in range(1, 18)]:
        r.fail(f"numéros de région inattendus : {abbr}")
    r.ok(f"17 régions administratives, de {min(s['population'] for s in states):,} à "
         f"{max(s['population'] for s in states):,} habitants")
    return sum(s["population"] for s in states)


def check_nation(r: Report, nat, states_total, communes):
    r.section("nation.json et total officiel")
    n = nat.get("nation") or {}
    official = n.get("population_official")
    if not official:
        return r.fail("population_official absente")
    if n.get("population") != official:
        r.fail(f"population {n.get('population')} ≠ total officiel {official}")
    else:
        r.ok(f"somme des SDR = total officiel du Québec : {official:,}")
    if states_total is not None and states_total != official:
        r.fail(f"somme des régions {states_total:,} ≠ {official:,}")
    elif states_total is not None:
        r.ok("somme des 17 régions = total officiel")
    if communes:
        col = {c: k for k, c in enumerate(communes["columns"])}
        rows = communes["rows"]
        tot = sum(row[col["pop"]] or 0 for row in rows)
        if len(rows) != N_CSD:
            r.fail(f"communes.json : {len(rows)} lignes au lieu de {N_CSD}")
        if tot != official:
            r.fail(f"communes.json : somme {tot:,} ≠ {official:,}")
        else:
            r.ok(f"communes.json : {len(rows)} SDR, somme = total officiel")
        nulls = [row[col["name"]] for row in rows if row[col["pop"]] is None]
        r.note(f"{len(nulls)} SDR sans chiffre publié (dénombrement partiel) : {', '.join(nulls)}")
    if nat.get("yields"):
        r.fail("nation.json définit des rendements sans données")


def check_lenses(r: Report, doc, ctx, web_dir, source_ids):
    r.section("lenses.json")
    lenses = doc.get("lenses") or []
    if not lenses:
        return r.fail("aucune lentille")
    groups = {g["id"] for g in doc.get("groups", [])}
    for lens in lenses:
        lid = lens["id"]
        vals = lens.get("values")
        if vals is None and lens.get("file"):
            p = web_dir / f"{lens['file']}.json"
            if not p.exists():
                r.fail(f"{lid} : fichier {lens['file']}.json absent")
                continue
            vals = json.loads(p.read_text())["values"]
        if lens.get("group") not in groups:
            r.fail(f"{lid} : groupe inconnu")
        if source_ids is not None and lens.get("source") not in source_ids:
            r.fail(f"{lid} : source {lens.get('source')} absente de sources.json")
        if ctx:
            if len(vals) != ctx["n"]:
                r.fail(f"{lid} : {len(vals)} valeurs au lieu de {ctx['n']}")
                continue
            off = sum(1 for v, o in zip(vals, ctx["owner"]) if o < 0 and v is not None)
            if off:
                r.fail(f"{lid} : {off} valeurs hors du Québec")
            bad = sum(1 for v in vals if v is not None and not (isinstance(v, (int, float)) and math.isfinite(v)))
            if bad:
                r.fail(f"{lid} : {bad} valeurs non numériques")
            filled = sum(1 for v, o in zip(vals, ctx["owner"]) if o >= 0 and v is not None)
            land = sum(1 for o in ctx["owner"] if o >= 0)
            r.ok(f"{lid} : {filled} / {land} hexagones du Québec ont une valeur, domaine {lens.get('domain')}")


def check_sources(r: Report, doc):
    r.section("sources.json")
    ids = set()
    for s in doc:
        ids.add(s["id"])
        if not s.get("license"):
            r.fail(f"{s['id']} : licence manquante")
        if not s.get("files"):
            r.warn(f"{s['id']} : aucun fichier cité (pas encore téléchargé ?)")
        for f in s.get("files", []):
            if not re.fullmatch(r"[0-9a-f]{64}", f.get("sha256", "")):
                r.fail(f"{s['id']} : {f.get('file')} sans sha256")
    r.ok(f"{len(doc)} sources, chacune avec sa licence : " + ", ".join(sorted(ids)))
    return ids


def check_icons(r: Report):
    r.section("icônes")
    icons = (WEB / "js" / "icons.js").read_text(encoding="utf-8")
    lens_doc = json.loads((WEB_DATA / "lenses.json").read_text()) if (WEB_DATA / "lenses.json").exists() else {}
    missing = [l["icon"] for l in lens_doc.get("lenses", []) if f"'{l['icon']}'" not in icons]
    if missing:
        r.fail(f"icônes absentes de web/js/icons.js : {missing}")
    else:
        r.ok("toutes les icônes de lentille existent")


def builder_checks(r: Report, web_dir: Path):
    from . import build as build_pkg
    for m in pkgutil.iter_modules(build_pkg.__path__):
        mod = importlib.import_module(f"{build_pkg.__name__}.{m.name}")
        fn = getattr(mod, "check", None)
        if not callable(fn):
            continue
        r.section(f"check de {m.name}")
        try:
            for level, msg in fn(web_dir):
                r._add(level, msg)
        except Exception as e:  # noqa: BLE001
            r.fail(f"{m.name}.check a levé {e!r}")


def run(web_dir: Path = WEB_DATA, quiet: bool = False) -> Report:
    r = Report(quiet)
    docs = {name: _load(r, web_dir, name, True) for name in REQUIRED}
    docs |= {name: _load(r, web_dir, name, False) for name in OPTIONAL}
    if any(docs[n] is None for n in REQUIRED):
        return r
    ctx = check_world(r, docs["world"])
    check_cities(r, docs["cities"], ctx)
    st_total = check_states(r, docs["states"], ctx)
    check_nation(r, docs["nation"], st_total, docs["communes"])
    source_ids = check_sources(r, docs["sources"])
    check_lenses(r, docs["lenses"], ctx, web_dir, source_ids)
    if web_dir == WEB_DATA:
        check_icons(r)
    builder_checks(r, web_dir)
    return r


def main() -> int:
    r = run()
    print(f"\n{r.count('PASS')} PASS, {r.count('NOTE')} NOTE, {r.count('WARN')} WARN, {r.count('FAIL')} FAIL")
    return 1 if r.failed else 0
