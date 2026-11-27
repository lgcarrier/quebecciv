import { css } from "../color.js";
import { esc, int, popShort, dec } from "../format.js";
import { isCapital } from "../world.js";
import { icon } from "./icon.js";
import { popLine, growthSpan, showPanel } from "./infoPanel.js";

/**
 * Opens the panel for region `idx` (index into world.json states / states.json): une région administrative.
 * ctx: {w, nation, states (states.json or null), cities, onClose, onPedia, onCity(city)}
 */
export function openStatePanel(idx, ctx) {
  const { w, nation } = ctx;
  const n = nation.nation;
  const geo = w.raw.states[idx] || {};
  let st = ctx.states?.[idx];
  if (st && geo.fips && st.fips && st.fips !== geo.fips) st = ctx.states.find((s) => s.fips === geo.fips);
  st = st || { ...geo };
  const name = st.name || geo.name || "Région";
  const abbr = st.abbr || geo.abbr || "";
  const count = ctx.states?.length || w.raw.states.length;

  const cities = (ctx.cities || []).filter((c) => (c.states || [])[0] === abbr).slice(0, 8);
  const cityRows = cities.length
    ? `<div class="city-list">${cities
        .map((c) => {
          const own = c.commune_population;
          const area = own != null && own !== c.population ? `<span class="muted cr-aire"> · agglo. ${popShort(c.population)}</span>` : "";
          const tip = own != null && own !== c.population
            ? `${int(own)} habitants à ${c.centre || c.name}, ${int(c.population)} dans sa RMR ou AR`
            : `${int(c.population)} habitants`;
          return `<button class="city-row" data-city="${esc(c.id)}" title="${esc(tip)}">
            <span class="cr-name">${isCapital(c) ? `${icon("capital", null, { size: 11, title: "Capitale nationale" })} ` : ""}${esc(c.name)}</span>
            <span class="cr-pop">${popShort(own ?? c.population)}${area}</span><span class="cr-go" aria-hidden="true">›</span></button>`;
        })
        .join("")}</div>`
    : `<p class="muted">Aucune ville (RMR, AR ou municipalité de 10 000 habitants ou plus) dont le noyau est dans cette région.</p>`;

  const rank = (k) => (st.ranks?.[k] ? ` <span class="muted">(${st.ranks[k]}<sup>${st.ranks[k] === 1 ? "re" : "e"}</sup> sur ${count})</span>` : "");
  const rows = [
    ["Population 2021", `${int(st.population)}${rank("population")}`],
    ["Superficie terrestre", st.land_km2 != null ? `${int(st.land_km2)} km²` : "–"],
    ["Densité", st.density != null ? `${st.density >= 100 ? int(st.density) : dec(st.density, 1)} hab./km²${rank("density")}` : "–"],
    ["Subdivisions de recensement", st.municipalities != null ? int(st.municipalities) : "–"],
    ["MRC et territoires équivalents", st.counties ? int(st.counties.length) : "–"],
  ];
  showPanel({
    kind: "state",
    stripe: css(w.stateColor[idx] || [190, 190, 190]),
    title: name,
    sub: `Région administrative ${esc(abbr)}`,
    headExtra: st.population != null ? popLine(st, growthSpan(st, n)) : "",
    sections: [
      { title: "En bref", html: rows.map(([k, v]) => `<div class="stat-row"><span class="sl">${esc(k)}</span><span><b>${v}</b></span></div>`).join("") },
      { title: "Plus grandes villes", html: cityRows },
      st.not_enumerated?.length && { title: "Sans chiffre publié", html: `<p class="muted">${esc(st.not_enumerated.join(", "))} : pas de population publiée par Statistique Canada pour 2021 ; non comptés dans le total.</p>` },
    ],
    foot: `Source : ${esc(nation.vintage)}. Rangs parmi les ${count} régions administratives (1 = la plus grande valeur).`,
    onClose: ctx.onClose,
    onPedia: ctx.onPedia,
    wire(panel) {
      panel.querySelectorAll("[data-city]").forEach((b) => {
        b.onclick = () => {
          const c = ctx.cities.find((x) => x.id === b.dataset.city);
          if (c) ctx.onCity(c);
        };
      });
    },
  });
}
