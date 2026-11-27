import { css } from "../color.js";
import { esc, int, dec } from "../format.js";
import { isCapital } from "../world.js";
import { icon } from "./icon.js";
import { popLine, growthSpan, showPanel, hidePanel } from "./infoPanel.js";

const KIND = { RMR: "Région métropolitaine de recensement", AR: "Agglomération de recensement", SDR: "Municipalité" };

/**
 * ctx: {w, nation, onClose, onPedia, onState(stateIndex)}
 */
export function openCityPanel(city, ctx) {
  const { w, nation } = ctx;
  const n = nation.nation;
  const owner = city.cell != null ? w.raw.owner[city.cell] : -1;
  const col = css(w.stateColor[owner] || [190, 190, 190]);

  // The city's regions as links to their panels (abbr = numéro de région administrative).
  const states = (city.states || [])
    .map((abbr) => ({ abbr, i: w.raw.states.findIndex((s) => s.abbr === abbr) }))
    .map(({ abbr, i }) => (i >= 0 && ctx.onState
      ? `<button class="chip" data-state="${i}" title="Ouvrir ${esc(w.raw.states[i].name)}">${esc(w.raw.states[i].name)}</button>`
      : `<span class="chip">${esc(abbr)}</span>`))
    .join("");

  const growth = growthSpan(city, n);
  const facts = [
    [KIND[city.kind] || "Ville", city.kind === "SDR" ? "hors de toute RMR ou AR" : `${int(city.municipalities)} municipalité${city.municipalities > 1 ? "s" : ""}`],
    ["Superficie terrestre", city.land_km2 != null ? `${int(city.land_km2)} km²` : "–"],
    ["Densité", city.density != null ? `${city.density >= 100 ? int(city.density) : dec(city.density, 1)} hab./km²` : "–"],
    ["Rang au Québec (population)", city.ranks?.population ? `${city.ranks.population}<sup>${city.ranks.population === 1 ? "er" : "e"}</sup>` : "–"],
    city.cross_border ? ["Population totale de la RMR", `${int(city.population_total)} (Ontario compris)`] : null,
  ].filter(Boolean);

  showPanel({
    kind: "city",
    stripe: col,
    title: city.name,
    titleHtml: `${isCapital(city) ? `<span class="cap">${icon("capital", null, { size: 13, title: "Capitale nationale" })}</span> ` : ""}${esc(city.name)}`,
    sub: `${esc(city.full || "")}${states ? `<div class="chips">${states}</div>` : ""}`,
    headExtra: popLine(city, growth),
    sections: [
      { title: "En bref", html: `<div class="city-facts">${facts.map(([k, v]) => `<div class="stat-row"><span class="sl">${esc(k)}</span><span><b>${v}</b></span></div>`).join("")}</div>` },
      { title: "Économie et rendements", html: `<p class="muted">Pas encore de données : les rendements (nourriture, production, or, science, culture), les emplois et le revenu seront ajoutés avec des sources ouvertes québécoises et canadiennes.</p>` },
    ],
    foot: `Population : ${esc(nation.vintage)} (somme des subdivisions de recensement québécoises${city.kind === "SDR" ? "" : " de la RMR ou de l'AR"}).`,
    onClose: ctx.onClose,
    onPedia: ctx.onPedia,
    wire(panel) {
      panel.querySelectorAll("[data-state]").forEach((b) => (b.onclick = () => ctx.onState(+b.dataset.state)));
    },
  });
}

export const closeCityPanel = hidePanel;
