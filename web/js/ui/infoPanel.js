// Shared building blocks for the city and state panels (both render into #city-panel).
import { compact, dec, dollars, esc, int, money, pct, signedPct, yieldValue } from "../format.js";
import { icon, glyph } from "./icon.js";

// Industry → a "district" glyph: SVG icons i-<key> from icons.js (no fallback glyph: the values stay null).
export const DISTRICT_ICON = {
  agriculture: null, mining: null, construction: null, manufacturing: null, wholesale: null, retail: null,
  transportation: null, utilities: null, information: null, finance: null, real_estate: null, professional: null,
  management: null, admin: null, education: null, health: null, arts: null, accommodation: null, other: null,
  public_admin: null,
};

const panelEl = () => document.getElementById("city-panel");

// Yield tiles; `ranks` (optional) adds "#3 of 49" under each.
export function yieldGrid(nation, yields, ranks = null, rankOf = 0) {
  return nation.yields
    .map((y) => {
      const v = yields?.[y.key];
      const r = ranks?.[y.key];
      const label = y.key === "gold" ? "GDP" : y.label;
      return `<div class="yield-tile" title="${esc(y.label)}${y.key === "gold" ? " (GDP)" : ""}: ${esc(y.description || "")}">
        <div class="ico" style="color:${esc(y.color)}">${glyph(y, 20)}</div>
        <div class="val" style="color:${esc(y.color)}">${yieldValue(y, v)}</div>
        <div class="lbl">${esc(label)}</div>
        ${r ? `<div class="rank" title="Rang parmi les ${rankOf} territoires de la carte (1 = le plus grand)">${r}<sup>e</sup> sur ${rankOf}</div>` : ""}</div>`;
    })
    .join("");
}

// One "value ▲ Europe value" row. higherIsGood: true / false / null (neutral).
export function statRow(ic, fallback, label, v, nv, fmt, higherIsGood) {
  let cmp = "";
  if (v != null && nv != null && nv !== 0) {
    const ratio = v / nv;
    const cls = Math.abs(ratio - 1) < 0.03 || higherIsGood == null ? "" : (higherIsGood ? ratio >= 1 : ratio <= 1) ? "good" : "bad";
    // Within 3% of the European value reads as level: no arrow, no colour (the colour uses the same band).
    const arrow = Math.abs(ratio - 1) < 0.03 ? "≈" : ratio > 1 ? "▲" : "▼";
    cmp = `<span class="cmp ${cls}">${arrow} Québec ${fmt(nv)}</span>`;
  }
  return `<div class="stat-row"><span class="sl">${icon(ic, fallback, { size: 14 })}${esc(label)}</span><span><b>${fmt(v)}</b>${cmp}</span></div>`;
}

// Purchasing power standards: euros at EU-average prices, comparable across countries.
const pps = (x) => (x == null ? "–" : `${int(x)} PPS`);

export function amenities(o, n) {
  return `
    ${statRow("unemployment", null, "Chômage", o.unemployment, n.unemployment, (x) => pct(x), false)}
    ${statRow("l-income", null, "Revenu disponible par habitant", o.median_income, n.median_income, pps, true)}
    ${o.poverty != null ? statRow("l-poverty", null, "Risque de pauvreté ou d'exclusion", o.poverty, n.poverty, (x) => pct(x), false) : ""}
    ${o.owners != null ? statRow("l-homeownership", null, "Propriétaires", o.owners, n.owners, (x) => pct(x), null) : ""}
    ${o.second_homes != null ? statRow("l-home", null, "Résidences secondaires", o.second_homes, n.second_homes, (x) => pct(x), null) : ""}
    ${o.home_value != null ? statRow("l-home", null, "Valeur médiane des logements", o.home_value, n.home_value, dollars, null) : ""}
    ${o.median_rent != null ? statRow("l-homeownership", null, "Loyer médian par mois", o.median_rent, n.median_rent, dollars, false) : ""}
    ${o.rent_burden != null ? statRow("l-burden", null, "Loyer ÷ revenu", o.rent_burden, n.rent_burden, (x) => pct(x), false) : ""}`;
}

// Workforce by industry with location quotients vs. the nation ("specialisation"). limit = max rows (0 = all).
export function industries(o, nation, limit = 0) {
  const n = nation.nation;
  const total = o.employed || 1;
  const nTotal = n.employed || 1;
  let rows = Object.entries(o.jobs || {})
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1]);
  if (limit) rows = rows.slice(0, limit);
  if (!rows.length) return `<p class="muted">Aucune donnée par industrie.</p>`;
  const maxShare = rows[0][1] / total;
  return rows
    .map(([k, v]) => {
      const share = v / total;
      const nShare = (n.jobs?.[k] || 0) / nTotal;
      const lq = nShare > 0 ? share / nShare : 1;
      const tip = `Part des emplois : ${dec(lq, 1)} fois sa part au Québec`;
      const badge = lq >= 1.3 ? `<span class="lq hi" title="${tip}">×${dec(lq, 1)}</span>`
        : lq <= 0.6 ? `<span class="lq lo" title="${tip}">×${dec(lq, 1)}</span>` : "";
      return `<div class="ind"><span aria-hidden="true">${icon(`i-${k}`, DISTRICT_ICON[k] || "•")}</span>
        <span>${esc(nation.industries?.[k] || k)}${badge}</span><span class="n">${compact(v)} · ${pct(share, 0)}</span>
        <div class="bar"><i style="width:${(share / maxShare) * 100}%;background:${lq >= 1.3 ? "#9fd76a" : "#c9a45c"}"></i></div></div>`;
    })
    .join("");
}

export const gdpRow = (o) =>
  o.gdp != null
    ? `<div class="stat-row"><span class="sl">${icon("y-gold", null, { size: 14 })}GDP${o.gdp_year ? ` (${o.gdp_year})` : ""}</span><span><b>${money(o.gdp)}</b>${
        o.population ? `<span class="cmp">${money(o.gdp / o.population)} par habitant</span>` : ""}</span></div>`
    : "";

// " · ▲ 3.4% since 2020" from growth / growth_years (cities and countries), compared with Europe in the tooltip.
// Empty when growth is missing (null means "not measured", never zero).
export function growthSpan(o, n = null) {
  if (!Number.isFinite(o?.growth)) return "";
  const yrs = Array.isArray(o.growth_years) && o.growth_years.length === 2 ? o.growth_years : null;
  const p = (g) => signedPct(g);
  const period = yrs ? `${yrs[0]}-${yrs[1]}` : "des dernières années";
  const us = Number.isFinite(n?.growth) ? ` (Québec ${p(n.growth)})` : "";
  const tip = `Variation de la population ${period}, recensements de Statistique Canada : ${p(o.growth)}${us}`;
  const cls = o.growth >= 0 ? "good" : "bad";
  return ` · <span class="growth ${cls}" title="${esc(tip)}">${o.growth >= 0 ? "▲" : "▼"} ${pct(Math.abs(o.growth))}${
    yrs ? ` <span class="since">depuis ${yrs[0]}</span>` : ""}</span>`;
}

// A city: the core city's own population, then its urban area's (the figures the panel's data describe), and the
// jobs located there. A country: its population and jobs.
export const popLine = (o, extra = "") => {
  const jobs = o.workplace_jobs != null ? ` · ${int(o.workplace_jobs)} emplois` : "";
  if (o.commune_population != null && o.centre && o.commune_population !== o.population) {
    return `<div class="cp-pop">${icon("pop", null, { size: 16 })} <b>${int(o.commune_population)}</b> habitants à ${esc(o.centre)}</div>
      <div class="cp-pop cp-pop2">${o.kind === "AR" ? "Agglomération" : "Région métropolitaine"}${o.cross_border ? " (partie québécoise)" : ""} : <b>${int(o.population)}</b> habitants${jobs}${extra}</div>`;
  }
  return `<div class="cp-pop">${icon("pop", null, { size: 16 })} <b>${int(o.population)}</b> habitants${jobs}${extra}</div>`;
};

/**
 * Fill and show the panel.
 * spec: {kind: "city"|"state", stripe, title, sub, headExtra, sections: [{title, html}], foot, onClose, onPedia, wire(panel)}
 */
export function showPanel(spec) {
  const panel = panelEl();
  panel.dataset.kind = spec.kind;
  panel.setAttribute("aria-label", `${spec.kind === "state" ? "Région" : "Ville"} : ${spec.title}`);
  panel.innerHTML = `
    <div class="sheet-grip" aria-hidden="true"></div>
    <div class="cp-head">
      <div class="stripe" style="background:${spec.stripe}"></div>
      <button class="icon-btn cp-close" aria-label="Fermer le panneau (Échap)" title="Fermer (Échap)">${icon("close", null, { size: 13 })}</button>
      <div class="cp-kind">${spec.kind === "state" ? "Région" : "Ville"}</div>
      <h2 class="cp-name">${spec.titleHtml ?? esc(spec.title)}</h2>
      ${spec.sub ? `<div class="cp-full">${spec.sub}</div>` : ""}
      ${spec.headExtra || ""}
    </div>
    ${spec.sections.filter(Boolean).map((s) => `<section class="cp-section"><h3>${s.title}</h3>${s.html}</section>`).join("")}
    <div class="cp-foot">${spec.foot || ""} <a href="#" data-pedia>Almanach ›</a></div>`;
  panel.hidden = false;
  panel.scrollTop = 0;
  panel.classList.remove("dragging-sheet");
  panel.style.transform = "";
  document.body.classList.add("panel-open");
  panel.querySelector(".cp-close").onclick = spec.onClose;
  panel.querySelector("[data-pedia]").onclick = (e) => {
    e.preventDefault();
    spec.onPedia?.();
  };
  spec.wire?.(panel);
}

export function hidePanel() {
  const panel = panelEl();
  panel.hidden = true;
  panel.innerHTML = "";
  delete panel.dataset.kind;
  document.body.classList.remove("panel-open");
}

// Bottom-sheet swipe-down to close (mobile). Installed once.
export function installSheetSwipe(onClose) {
  const panel = panelEl();
  let start = null;
  panel.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse" || !matchMedia("(max-width: 700px)").matches) return;
    // Only from the grip/head, or anywhere while the sheet is scrolled to the top.
    const fromHead = e.target.closest(".sheet-grip, .cp-head");
    if (!fromHead && panel.scrollTop > 0) return;
    if (e.target.closest("button, a, input")) return;
    start = { y: e.clientY, id: e.pointerId, dy: 0, head: !!fromHead };
  });
  panel.addEventListener("pointermove", (e) => {
    if (!start || e.pointerId !== start.id) return;
    start.dy = Math.max(0, e.clientY - start.y);
    if (start.dy > 6 && (start.head || panel.scrollTop <= 0)) {
      panel.classList.add("dragging-sheet");
      panel.style.transform = `translateY(${start.dy}px)`;
    }
  });
  const end = (e) => {
    if (!start || e.pointerId !== start.id) return;
    const dy = start.dy;
    start = null;
    panel.classList.remove("dragging-sheet");
    panel.style.transform = "";
    if (dy > 80) onClose();
  };
  panel.addEventListener("pointerup", end);
  panel.addEventListener("pointercancel", end);
}
