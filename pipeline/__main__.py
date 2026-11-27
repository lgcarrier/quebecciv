"""Command line:  uv run python -m pipeline <command> [names...]

  fetch   [source ...]   download raw files (cached; --force to re-download)
  process [source ...]   raw → data/interim/<source>.json
  build   [builder ...]  interim → web/data/*.json, in dependency order. Up-to-date
                         builders are skipped (--force rebuilds); --deps also runs
                         the upstream builders of the named ones
  check                  validate web/data/*.json and print a data-quality report
  all                    fetch + process + build everything, then check
  list                   show sources and builders
  serve                  serve web/ on http://127.0.0.1:8765

--offline: never touch the network. core.fetch.OFFLINE is set, so download() of a
cached file is a no-op and of a missing one (or any url_exists()) raises OfflineError,
and sources skip their discovery requests ("is there a newer year?") and use their
newest cached release instead. 'fetch' then only checks that every needed raw file
is cached, listing the sources that are incomplete, so 'all --offline' fails
before processing anything when a file is missing. (--force can't be combined.)

--light: leave out the optional sources (nrcan_landcover, a 2.1 GB download) when no
source is named: fetch skips them, process skips those that were never downloaded, and
the builders do without their interim. The map is then built WITHOUT land cover (the
land is coloured by elevation and the land lenses are left out): fine for working on
the rest of the map, not for committing web/data.
"""

from __future__ import annotations

import argparse
import ast
import functools
import http.server
import json
import urllib.parse
import sys
import time
from pathlib import Path
from types import ModuleType

from .build import BUILDERS
from .core import fetch
from .core.paths import INTERIM, ROOT, WEB, WEB_DATA
from .core.store import save_interim
from .sources import BY_ID, SOURCES


def _pick(names, registry, kind):
    if not names:
        return list(registry)
    unknown = [n for n in names if n not in registry]
    if unknown:
        sys.exit(f"unknown {kind}: {', '.join(unknown)}  (try: list)")
    return names


def _without_optional(ids, names, light, keep=lambda sid: False):
    """`ids` minus the optional sources under --light (only when no source was named; `keep(sid)` spares one)."""
    if not light or names:
        return ids
    out = []
    for sid in ids:
        if BY_ID[sid].optional and not keep(sid):
            print(f"[--light] {sid}: optional source left out")
        else:
            out.append(sid)
    return out


def cmd_fetch(names, force=False, light=False):
    if fetch.OFFLINE and force:
        sys.exit("--force re-downloads, which --offline forbids")
    missing = []
    for sid in _without_optional(_pick(names, BY_ID, "source"), names, light):
        print(f"[fetch] {sid}{' (--offline: checking the cache)' if fetch.OFFLINE else ''}")
        if not fetch.OFFLINE:
            BY_ID[sid].fetch(force=force)
            continue
        try:
            BY_ID[sid].fetch()
        except (fetch.OfflineError, FileNotFoundError) as exc:
            print(f"    ! {exc}")
            missing.append(sid)
    if missing:
        sys.exit(f"--offline: raw files missing for {', '.join(missing)} (run fetch without --offline)")


def _process_order(ids: list[str]) -> list[str]:
    """`ids` with each source after those its class lists in `after` (e.g. gisco and eurostat merge uk_ons)."""
    order, seen = [], set()

    def visit(sid):
        if sid in seen:
            return
        seen.add(sid)
        for dep in getattr(BY_ID[sid], "after", ()):
            if dep in ids:
                visit(dep)
        order.append(sid)

    for sid in ids:
        visit(sid)
    return order


def cmd_process(names, light=False):
    # Under --light an optional source is still processed when its raw files are already here.
    ids = _without_optional(_pick(names, BY_ID, "source"), names, light, keep=lambda sid: bool(fetch.read_manifest(sid)))
    for sid in _process_order(ids):
        t = time.time()
        print(f"[process] {sid}")
        data = BY_ID[sid].process()
        # save_interim moves "_files" (raw files used) into the payload for the catalog.
        save_interim(sid, data, vintage=data.pop("vintage", None))
        print(f"    done in {time.time() - t:.1f}s")


# ---------------------------------------------------------------- build planning


def output_path(name: str) -> Path:
    """Where a REQUIRES/PRODUCES name lives: "_x" and sources → data/interim, "x.json" → web/data."""
    if name.startswith("_") or not name.endswith(".json"):
        return INTERIM / f"{name}.json"
    return WEB_DATA / name


def select_builders(names, builders: dict[str, ModuleType], with_deps: bool = False) -> list[str]:
    """Builder names to run, in the registry's dependency order.

    No names → all of them. With `with_deps`, upstream producers of the named
    builders' REQUIRES are added transitively.
    """
    chosen = set(_pick(names, builders, "builder"))
    if with_deps:
        producer = {out: n for n, m in builders.items() for out in m.PRODUCES}
        todo = list(chosen)
        while todo:
            for req in getattr(builders[todo.pop()], "REQUIRES", []):
                up = producer.get(req)
                if up and up not in chosen:
                    chosen.add(up)
                    todo.append(up)
    return [n for n in builders if n in chosen]


def helper_files(module_file: Path, seen: set[Path] | None = None) -> set[Path]:
    """The module file plus sibling modules it imports relatively (e.g. build/yields.py), transitively."""
    module_file = Path(module_file)
    seen = set() if seen is None else seen
    if module_file in seen or not module_file.exists():
        return seen
    seen.add(module_file)
    for node in ast.walk(ast.parse(module_file.read_text())):
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            names = [node.module] if node.module else [a.name for a in node.names]
            for n in names:
                helper_files(module_file.parent / f"{n.split('.')[0]}.py", seen)
    return seen


def is_stale(mod: ModuleType) -> bool:
    """True unless every PRODUCES output exists and is newer than all REQUIRES interims, the OPTIONAL interims that
    exist, and the code."""
    outs = [output_path(p) for p in mod.PRODUCES]
    if not outs or not all(p.exists() for p in outs):
        return True
    inputs = [output_path(r) for r in getattr(mod, "REQUIRES", [])]
    if not all(p.exists() for p in inputs):
        return True  # let build() fail with its own clear message
    inputs += [p for p in (output_path(r) for r in getattr(mod, "OPTIONAL", [])) if p.exists()]
    inputs += helper_files(Path(mod.__file__))
    return max((p.stat().st_mtime for p in inputs), default=0) >= min(p.stat().st_mtime for p in outs)


def cmd_build(names, force=False, with_deps=False, builders=None):
    builders = BUILDERS if builders is None else builders
    for name in select_builders(names, builders, with_deps):
        mod = builders[name]
        if not (force or getattr(mod, "RUN_LAST", False) or is_stale(mod)):
            print(f"[build] {name}: up to date (--force to rebuild)")
            continue
        t = time.time()
        print(f"[build] {name}")
        mod.build()
        print(f"    done in {time.time() - t:.1f}s")


def cmd_check() -> int:
    from . import check

    return check.main()


def cmd_list():
    print("sources:")
    for s in SOURCES:
        print(f"  {s.id:20} {s.info.title}{' (optional: --light leaves it out)' if s.optional else ''}")
    print("builders (in order):")
    for name, mod in BUILDERS.items():
        opt = getattr(mod, "OPTIONAL", [])
        print(f"  {name:20} needs {', '.join(mod.REQUIRES) or '-'}{'; optional: ' + ', '.join(opt) if opt else ''}")


# Self-unregistering service worker, served at /sw.js by the dev server only. quebecciv has no service worker, but
# other local apps served earlier on the same origin (http://127.0.0.1:8765) may have left one registered at scope
# "/" (several projects on this machine register ./sw.js). Such a worker keeps intercepting quebecciv's requests until
# a hard reload (Ctrl+Maj+R) bypasses it. The browser re-fetches the worker's script on navigation; it gets this one,
# which unregisters itself and reloads its pages.
KILL_SW = b"""self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil((async () => {
  await self.registration.unregister();
  for (const c of await self.clients.matchAll({ type: "window" })) c.navigate(c.url);
})()));
"""


class _DevHandler(http.server.SimpleHTTPRequestHandler):
    """Static files of web/ (no API: the daily challenge is not part of quebecciv yet).

    * Cache-Control: no-cache on every response, so the browser revalidates (If-Modified-Since → 304) instead of
      reusing a stale heuristic-cached module or stylesheet after a rebuild or after another app on the same port.
    * HTTP/1.1 keep-alive: the ~50 ES modules reuse a few connections instead of opening one each.
    * /sw.js answers with KILL_SW (see above)."""

    protocol_version = "HTTP/1.1"
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript",
                      ".json": "application/json"}

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_GET(self):
        if urllib.parse.urlsplit(self.path).path == "/sw.js":
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript")
            self.send_header("Content-Length", str(len(KILL_SW)))
            self.end_headers()
            self.wfile.write(KILL_SW)
            return
        super().do_GET()


class _DevServer(http.server.ThreadingHTTPServer):
    request_queue_size = 128  # socketserver's default listen backlog is 5
    daemon_threads = True


def cmd_serve(port=8765):
    handler = functools.partial(_DevHandler, directory=str(WEB))
    with _DevServer(("127.0.0.1", port), handler) as srv:
        print(f"serving web/ at http://127.0.0.1:{port}")
        srv.serve_forever()


def main(argv=None):
    p = argparse.ArgumentParser(prog="pipeline", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("command", choices=["fetch", "process", "build", "check", "all", "list", "serve"])
    p.add_argument("names", nargs="*")
    p.add_argument("--force", action="store_true", help="fetch: re-download even if cached; build: rebuild even if up to date")
    p.add_argument("--deps", action="store_true", help="build: also run upstream builders of the named ones")
    p.add_argument("--offline", action="store_true", help="use cached downloads only; never touch the network")
    p.add_argument("--light", action="store_true",
                   help="fetch/process/all: leave out the optional sources (the 2.1 GB land cover); no land cover on the map")
    p.add_argument("--port", type=int, default=8765)
    a = p.parse_args(argv)
    fetch.OFFLINE = a.offline
    if a.command == "fetch":
        cmd_fetch(a.names, a.force, a.light)
    elif a.command == "process":
        cmd_process(a.names, a.light)
    elif a.command == "build":
        cmd_build(a.names, a.force, a.deps)
    elif a.command == "check":
        sys.exit(cmd_check())
    elif a.command == "all":
        cmd_fetch([], a.force, a.light)
        cmd_process([], a.light)
        cmd_build([], a.force)
        if cmd_check():  # WARNs are reported but don't fail the run; FAILs do
            sys.exit(1)
    elif a.command == "list":
        cmd_list()
    elif a.command == "serve":
        cmd_serve(a.port)


if __name__ == "__main__":
    main()
