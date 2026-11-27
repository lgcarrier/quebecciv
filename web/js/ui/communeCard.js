// The place card: what the search box opens for a municipality or town (communes.json row). It sits under the top
// bar until closed, and offers to open the place's urban area or its country.
import { dollars, esc, int, signedPct } from "../format.js";
import { icon } from "./icon.js";

/**
 * opts: {cityById: Map, stateName(abbr) → string, onCity(city), onState(abbr), onClose(), onShare()?}
 * Returns {show(commune), hide(), get isOpen}.
 */
export function createCommuneCard(opts) {
  const el = document.createElement("aside");
  el.className = "panel commune-card";
  el.setAttribute("role", "region");
  el.setAttribute("aria-label", "Fiche du lieu");
  el.hidden = true;
  document.body.appendChild(el);

  const row = (ic, fb, label, value, sub = "") =>
    value == null || value === "" ? "" : `<div class="cc-row"><span class="cc-l">${icon(ic, fb, { size: 14 })}${esc(label)}</span>
      <span class="cc-v"><b>${value}</b>${sub ? `<small>${sub}</small>` : ""}</span></div>`;

  function show(c) {
    const city = c.aav ? opts.cityById.get(c.aav) : null;
    const dep = opts.stateName(c.dep) || c.dep;
    const town = false; // toutes les lignes sont des subdivisions de recensement de Statistique Canada
    el.innerHTML = `
      <button class="icon-btn cc-close" type="button" aria-label="Fermer la fiche">${icon("close", null, { size: 12 })}</button>
      <h2 class="cc-name">${esc(c.name)}</h2>
      <div class="cc-kind">${esc(c.kind || "Subdivision de recensement")}, ${esc(dep)}</div>
      <div class="cc-rows">
        ${row("pop", null, "Population (Recensement de 2021)", c.pop != null ? int(c.pop) : "non publiée", c.growth != null ? `${signedPct(c.growth)} depuis 2016` : "")}
        ${row("l-developed", null, "Densité", c.density != null ? `${int(c.density)} hab./km²` : null)}
        
      </div>
      <div class="cc-code">Code de SDR (Statistique Canada) ${esc(c.code)}</div>
      <div class="cc-actions">
        ${city ? `<button type="button" class="btn cc-city">${icon("pop", null, { size: 14 })}<span>${esc(city.name)}</span></button>` : `<span class="cc-none">Hors RMR et AR</span>`}
        <button type="button" class="btn cc-dep">${icon("terrain", null, { size: 14 })}<span>${esc(dep)}</span></button>
        ${opts.onShare ? `<button type="button" class="btn cc-share">${icon("share", null, { size: 14 })}<span>Copier le lien</span></button>` : ""}
      </div>`;
    el.hidden = false;
    el.querySelector(".cc-close").onclick = () => hide(true);
    el.querySelector(".cc-city")?.addEventListener("click", () => { hide(false); opts.onCity(city); });
    el.querySelector(".cc-dep").onclick = () => { hide(false); opts.onState(c.dep); };
    el.querySelector(".cc-share")?.addEventListener("click", () => opts.onShare());
  }

  function hide(notify = true) {
    if (el.hidden) return;
    el.hidden = true;
    if (notify) opts.onClose?.();
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !el.hidden) hide(true);
  });

  return { show, hide, get isOpen() { return !el.hidden; } };
}
