// Top-bar search over cities, countries and (loaded on the first keystroke) every municipality: prefix matches first,
// then word-prefix, then substring; ties by population.
import { esc, popShort } from "../format.js";
import { icon } from "../ui/icon.js";

// Letters NFD does not decompose, so "Kobenhavn" finds København and "Lodz" Łódź.
const FOLD = { "ø": "o", "æ": "ae", "œ": "oe", "ß": "ss", "ł": "l", "đ": "d", "ð": "d", "þ": "th", "ı": "i" };
const norm = (s) => String(s || "").toLowerCase().replace(/[øæœßłđðþı]/g, (ch) => FOLD[ch]).normalize("NFD")
  .replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, " ").trim();
const MAX = 8;

/**
 * opts: {cities, states (list of {name, abbr, population?}), loadCommunes?() → Promise<communes.json>,
 *        onPick({kind:'city'|'state'|'commune', city?, index?, commune?})}
 */
export function initSearch(opts) {
  const input = document.getElementById("search-input");
  const box = document.getElementById("search-results");
  if (!input || !box) return { focus() {}, close() {}, get isOpen() { return false; } };
  // The full placeholder only fits the wide search box; narrower ones say just "Search".
  const narrow = matchMedia("(max-width: 1120px)");
  const setPlaceholder = () => (input.placeholder = narrow.matches ? "Chercher…" : "Chercher un lieu, une ville, une région");
  setPlaceholder();
  narrow.addEventListener?.("change", setPlaceholder);

  const entries = [];
  for (const c of opts.cities || []) {
    entries.push({ kind: "city", city: c, name: c.name, n: norm(c.name), alias: norm(c.local_name), full: norm(c.full), pop: c.population || 0,
      sub: c.full || "", label: c.name });
  }
  (opts.states || []).forEach((s, index) => {
    if (!s) return;
    entries.push({ kind: "state", index, name: s.name, n: norm(s.name), alias: norm(s.local_name), full: norm(s.abbr), abbr: (s.abbr || "").toLowerCase(),
      pop: s.population || 0, sub: s.abbr ? `Région administrative (${s.abbr})` : "Région administrative", label: s.name });
  });

  // Places (communes.json: every local administrative unit, plus GeoNames towns where there are none) load on the
  // first keystroke and join the entries when they arrive.
  const depName = Object.fromEntries((opts.states || []).filter(Boolean).map((s) => [s.abbr, s.name]));
  let communesState = opts.loadCommunes ? "idle" : "none";
  function loadCommunes() {
    if (communesState !== "idle") return;
    communesState = "loading";
    opts.loadCommunes().then((d) => {
      if (!d?.rows) { communesState = "none"; return; }
      const col = Object.fromEntries(d.columns.map((c, k) => [c, k]));
      for (const r of d.rows) {
        const c = Object.fromEntries(d.columns.map((name, k) => [name, r[k]]));
        entries.push({ kind: "commune", commune: c, name: c.name, n: norm(c.name), full: norm(c.code), pop: c.pop || 0,
          sub: `${c.kind || "Municipalité"}, ${depName[c.dep] || c.dep || "Québec"}`, label: c.name, code: r[col.code] });
      }
      communesState = "ready";
      if (input.value.trim() && document.activeElement === input) {
        results = query(input.value);
        sel = results.length ? 0 : -1;
        render();
      }
    }, () => { communesState = "none"; });
  }
  let results = [];
  let sel = -1;

  function score(e, q) {
    if (e.abbr && e.abbr === q) return 0;
    if (e.code && e.code === q) return 0; // a place's GISCO code
    if (e.n.startsWith(q)) return e.n === q ? 0 : 1;
    // the local name: München, Warszawa, Deutschland, Suomi
    if (e.alias && e.alias.startsWith(q)) return e.alias === q ? 0 : 1;
    if (e.alias && (" " + e.alias).includes(" " + q)) return 2;
    if ((" " + e.n).includes(" " + q)) return 2;
    if ((" " + e.full).includes(" " + q)) return 3;
    if (e.n.includes(q)) return 4;
    if (e.full.includes(q)) return 5;
    return -1;
  }

  function query(q) {
    q = norm(q);
    if (!q) return [];
    const out = [];
    for (const e of entries) {
      const s = score(e, q);
      if (s >= 0) out.push([s, e]);
    }
    out.sort((a, b) => a[0] - b[0] || b[1].pop - a[1].pop);
    return out.slice(0, MAX).map((x) => x[1]);
  }

  function position() {
    const r = input.getBoundingClientRect();
    const width = Math.min(Math.max(r.width, 320), window.innerWidth - 16);
    box.style.top = r.bottom + 6 + "px";
    box.style.left = Math.max(8, Math.min(window.innerWidth - width - 8, r.left)) + "px";
    box.style.width = width + "px";
  }

  function render() {
    if (!results.length) {
      const loading = communesState === "loading";
      box.innerHTML = input.value.trim() ? `<div class="sr-empty">${loading ? "Chargement des lieux…" : `Aucun lieu, aucune ville ni région ne correspond à « ${esc(input.value.trim())} »`}</div>` : "";
      box.hidden = !input.value.trim();
      input.setAttribute("aria-expanded", String(!box.hidden));
      input.removeAttribute("aria-activedescendant");
      if (!box.hidden) position();
      return;
    }
    box.innerHTML = results
      .map((e, i) => `<div class="sr-item ${i === sel ? "sel" : ""}" role="option" id="sr-${i}" aria-selected="${i === sel}" data-i="${i}">
        <span class="sr-ic">${e.kind === "state" ? icon("terrain", null, { size: 16 }) : e.kind === "commune" ? icon("l-home", null, { size: 16 }) : icon("pop", null, { size: 16 })}</span>
        <span class="sr-main"><b>${esc(e.label)}</b><span class="sr-sub">${esc(e.sub)}</span></span>
        <span class="sr-pop">${e.pop ? popShort(e.pop) : ""}</span></div>`)
      .join("");
    box.hidden = false;
    input.setAttribute("aria-expanded", "true");
    if (sel >= 0) input.setAttribute("aria-activedescendant", `sr-${sel}`);
    else input.removeAttribute("aria-activedescendant");
    position();
  }

  function choose(i) {
    const e = results[i];
    if (!e) return;
    close();
    input.value = "";
    input.blur();
    opts.onPick(e.kind === "city" ? { kind: "city", city: e.city } : e.kind === "commune" ? { kind: "commune", commune: e.commune }
      : { kind: "state", index: e.index });
  }

  function close() {
    box.hidden = true;
    results = [];
    sel = -1;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  }

  input.addEventListener("input", () => {
    if (input.value.trim().length >= 2) loadCommunes();
    results = query(input.value);
    sel = results.length ? 0 : -1;
    render();
  });
  input.addEventListener("focus", () => {
    if (input.value.trim()) {
      results = query(input.value);
      sel = results.length ? 0 : -1;
      render();
    }
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!results.length) return;
      sel = (sel + (e.key === "ArrowDown" ? 1 : -1) + results.length) % results.length;
      render();
      box.querySelector(".sel")?.scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (results.length) choose(Math.max(0, sel));
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      if (!box.hidden && input.value) { input.value = ""; close(); }
      else { close(); input.blur(); }
    }
  });
  input.addEventListener("blur", () => setTimeout(() => {
    if (document.activeElement !== input) close();
  }, 150));
  box.addEventListener("pointerdown", (e) => e.preventDefault()); // keep focus in the input
  box.addEventListener("click", (e) => {
    const it = e.target.closest(".sr-item");
    if (it) choose(+it.dataset.i);
  });
  box.addEventListener("pointermove", (e) => {
    const it = e.target.closest(".sr-item");
    if (it && +it.dataset.i !== sel) {
      sel = +it.dataset.i;
      box.querySelectorAll(".sr-item").forEach((x, i) => {
        x.classList.toggle("sel", i === sel);
        x.setAttribute("aria-selected", String(i === sel));
      });
    }
  });
  window.addEventListener("resize", () => !box.hidden && position());

  return {
    focus() {
      input.focus();
      input.select();
    },
    close() {
      close();
      input.blur();
    },
    query,
    get isOpen() { return document.activeElement === input || !box.hidden; },
  };
}
