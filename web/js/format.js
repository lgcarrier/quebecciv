// Formatage des nombres à la québécoise (fr-CA) : virgule décimale, espace insécable fine entre les milliers et
// devant les unités (12 %, 1,2 M), dollars après le nombre (42 350 $). Les noms des fonctions restent ceux d'usaciv
// et d'europeciv pour que tous les imports fonctionnent.

/** Séparateur entre un nombre et son unité (%, k, M, G, °C) : espace insécable fine. */
export const NNBSP = "\u202f";

/** x.toFixed(d) avec la virgule décimale. */
export const dec = (x, d = 0) => x.toFixed(d).replace(".", ",");

export function compact(n) {
  if (n == null || Number.isNaN(n)) return "–";
  const a = Math.abs(n);
  if (a >= 1e12) return dec(n / 1e12, a >= 1e13 ? 1 : 2) + NNBSP + "T";
  if (a >= 1e9) return dec(n / 1e9, a >= 1e11 ? 0 : 1) + NNBSP + "G";
  if (a >= 1e6) return dec(n / 1e6, a >= 1e8 ? 0 : 1) + NNBSP + "M";
  if (a >= 1e3) return dec(n / 1e3, a >= 1e5 ? 0 : 1).replace(/,0$/, "") + NNBSP + "k";
  return String(Math.round(n));
}

const minus = (n) => (n < 0 ? "−" : "");

/** Dollars abrégés : 92,3 G$, 1,2 M$, 34 k$, 850 $. */
export const money = (n) => (n == null ? "–" : minus(n) + (Math.abs(n) >= 1e3 ? compact(Math.abs(n)) + "$" : Math.round(Math.abs(n)) + NNBSP + "$"));
/** Dollars entiers : 42 350 $. (Garde son nom d'usaciv pour que tous les imports fonctionnent.) */
export const dollars = (n) => (n == null ? "–" : minus(n) + Math.round(Math.abs(n)).toLocaleString("fr-CA") + NNBSP + "$");
export const euros = dollars;
export const int = (n) => (n == null ? "–" : Math.round(n).toLocaleString("fr-CA"));
export const pct = (x, d = 1) => (x == null ? "–" : dec(x * 100, d) + NNBSP + "%");
/** Pourcentage signé : +2,1 %, −0,4 %. */
export const signedPct = (g, d = 1) => (g == null || !Number.isFinite(g) ? "–" : `${g >= 0 ? "+" : "−"}${dec(Math.abs(g * 100), d)}${NNBSP}%`);

export function yieldValue(y, v) {
  return y.unit === "usd" || y.unit === "eur" || y.unit === "cad" ? money(v) : compact(v);
}

export function popShort(n) {
  if (n >= 1e7) return Math.round(n / 1e6) + NNBSP + "M";
  if (n >= 1e6) return dec(n / 1e6, 1) + NNBSP + "M";
  if (n < 1e3) return String(Math.round(n));
  return Math.round(n / 1e3) + NNBSP + "k";
}

/** Real km per map unit (world.json km_per_unit; the map may be drawn at a different scale than real km). */
export const kmPerUnit = (world) => (world && Number.isFinite(world.km_per_unit) && world.km_per_unit > 0 ? world.km_per_unit : 1);

export const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
