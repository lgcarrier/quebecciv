// The Almanac: what every number means and exactly where it comes from.
import { resolveTables } from "../terrain.js";
import { esc, kmPerUnit } from "../format.js";
import { icon, glyph } from "./icon.js";

const COVER_ICON = { forest_deciduous: "l-forest", forest_evergreen: "l-forest", forest_mixed: "l-forest", cropland: "l-farmland", pasture: "l-farmland", urban: "l-developed" };
// Page ids stay as they are (other modules open pages by id); LABEL is what the reader sees.
const LABEL = { "About this map": "À propos", States: "Régions", Terrain: "Terrain", Lenses: "Lentilles", Sources: "Sources" };
const frNum = (v) => (typeof v === "number" ? v.toLocaleString("fr-CA") : String(v));

export function initPedia(data) {
  const modal = document.getElementById("pedia");
  const card = modal.querySelector(".modal-card");
  const nav = document.getElementById("pedia-nav");
  const body = document.getElementById("pedia-body");
  const srcName = (id) => data.sources?.find((s) => s.id === id)?.title || id || "";
  let restoreFocus = null;

  const h2 = (ic, fb, text) => `<h2>${icon(ic, fb, { size: 24 })}<span>${esc(text)}</span></h2>`;
  const n = data.nation.nation || {};
  const hexKm = Math.round(data.world.grid.radius * kmPerUnit(data.world) * 10) / 10;

  const pages = {
    "About this map": () => `
      ${h2("pedia", null, "À propos de cette carte")}
      <p>Le vrai Québec, dessiné comme une carte de jeu de stratégie : ses 17 régions administratives, ses
      ${frNum(n.municipalities)} municipalités, réserves, terres réservées, villages nordiques et territoires non organisés
      (les subdivisions de recensement de Statistique Canada) et ses villes. Rien n'est inventé : chaque hexagone, ville
      et nombre vient de données publiques, citées sous <i>Sources</i>.</p>
      <h4>Comment c'est construit</h4>
      <p>Le Québec est projeté (azimutale équivalente de Lambert, centrée sur le Québec : chaque hexagone couvre la même
      superficie réelle) et découpé en ${data.world.grid.cols}×${data.world.grid.rows} hexagones de ${frNum(hexKm)} km de rayon
      (environ 65 km² chacun). Un hexagone appartient à la région et à la MRC (division de recensement) qui couvrent la
      majorité de ses points d'échantillonnage ; le relief vient des altitudes ETOPO1 à l'intérieur de l'hexagone.</p>
      <p><b>Les villes</b> sont les régions métropolitaines de recensement (RMR) et agglomérations de recensement (AR) de
      Statistique Canada (un noyau urbain et les municipalités qui y sont liées par les déplacements domicile-travail),
      plus les municipalités de 10 000 habitants ou plus qui n'en font partie d'aucune. Pour Ottawa–Gatineau, seule la
      partie québécoise est comptée.</p>
      <p><b>Pas encore là</b> : les rendements (nourriture, production, or…), l'économie, les ressources, les routes, les
      conseillers, les classements et le défi quotidien de la version européenne. Ils reviendront quand des données
      québécoises ouvertes les alimenteront ; rien n'est simulé en attendant.</p>
      <h4>Commandes</h4>
      <p>Glisser ou flèches / WASD pour se déplacer · molette, +/– ou double-clic pour zoomer · clic sur une ville ou une
      région pour l'ouvrir · / ou ⌘K pour chercher un lieu · L pour changer de lentille · ? pour tous les raccourcis ·
      Échap pour fermer.</p>
      <p class="muted">D'après <a href="https://github.com/lmveprog/Europe-Civilization" target="_blank" rel="noopener">Europe-Civilization</a>
      (lmveprog), lui-même tiré d'<a href="https://karpathy.ai/usaciv/" target="_blank" rel="noopener">usaciv</a>
      d'Andrej Karpathy, licence MIT.</p>`,
    States: () => `
      ${h2("terrain", null, "Régions administratives")}
      <p>Cliquez sur un hexagone sans ville pour ouvrir sa région. Les 17 régions administratives du Québec correspondent
      aux 17 régions économiques du Recensement de 2021 ; leur population est la somme de leurs subdivisions de
      recensement (${esc(data.nation.vintage)}), donc les campagnes comptent autant que les villes.</p>
      <p><b>Rangs</b> (« 3<sup>e</sup> sur 17 ») : 1 = la plus grande valeur.</p>
      <p class="muted">${n.not_enumerated?.length ? `Sans chiffre publié par Statistique Canada (« .. ») : ${esc(n.not_enumerated.join(", "))}. Ces lieux sont sur la carte, sans population, et ne comptent pas dans les totaux, comme dans le total officiel.` : ""}</p>`,
    Terrain: () => {
      const t = data.w?.tables || resolveTables(data.world.tables);
      const row = (x) => `<tr><td class="nm">${x.color ? `<span class="swatch" style="background:${esc(x.color)}"></span>` : ""}${
        COVER_ICON[x.key] ? icon(COVER_ICON[x.key], "", { size: 15 }) + " " : ""}<b>${esc(x.name)}</b></td><td>${esc(x.rule || "")}</td></tr>`;
      const notes = data.world.tables?.notes || {};
      return `
      ${h2("terrain", null, "Terrain")}
      <p>Chaque hexagone fait la moyenne des altitudes ETOPO1 qu'il contient. Le relief vient de cette moyenne et de la
      rugosité (écart type) ; l'ombrage, des différences d'altitude avec les hexagones voisins, éclairés du nord-ouest.</p>
      <h4>${icon("l-forest", null, { size: 16 })} Couverture du sol</h4>
      <p class="muted">${esc(notes.cover || "Pas encore de couverture du sol : la terre est colorée selon l'altitude.")}</p>
      <h4>Relief</h4>
      <table>${t.relief.map(row).join("")}</table>
      <p class="muted">${esc(notes.relief || "")}</p>
      <h4>${icon("r-hydro", null, { size: 16 })} Eau</h4>
      <table>${t.water.filter((x) => x.id > 0).map(row).join("")}</table>
      <p class="muted">${esc(notes.water || "")}</p>
      <h4>Au-delà des frontières</h4>
      <p class="muted">L'Ontario, le Nouveau-Brunswick, Terre-Neuve-et-Labrador, la Nouvelle-Écosse, l'Île-du-Prince-Édouard,
      le Nunavut et les États-Unis sont dessinés sous un léger brouillard, pour le contexte seulement. Les frontières
      sont celles des fichiers de Statistique Canada (y compris la frontière Québec–Labrador telle qu'elle y est tracée).</p>`;
    },
    Lenses: () => `
      ${h2("layers", null, "Lentilles")}
      <p>Les lentilles recolorent la carte selon une mesure (${esc(data.lenses.vintage)}). La population de chaque
      subdivision de recensement est répartie sur les hexagones au prorata de sa superficie terrestre : c'est une
      approximation, une grande municipalité rurale paraît uniformément peuplée.</p>
      <p>La légende montre combien d'hexagones tombent à chaque valeur. Survolez-la ou glissez dessus pour ne montrer que
      cette plage sur la carte.</p>
      ${(data.lenses.groups || [{ id: null, name: "" }]).map((g) => {
        const ls = data.lenses.lenses.filter((l) => !g.id || l.group === g.id);
        if (!ls.length) return "";
        return `${g.name ? `<h3 class="grp">${icon(`g-${g.id}`, "", { size: 16 })} ${esc(g.name)}</h3>` : ""}${ls.map((l) => `
          <div class="lens-entry"><div class="le-ic">${glyph(l, 26)}</div><div>
          <h4>${esc(l.name)}</h4><p>${esc(l.description)}${l.note ? `<br><i>${esc(l.note)}</i>` : ""}<br>
          <i class="le-ramp" style="background:linear-gradient(90deg, ${(l.ramp || []).map(esc).join(",")})"></i>
          <span class="muted">Échelle : ${l.scale === "log" ? "logarithmique" : "linéaire"}, ${frNum(l.domain[0])} à ${frNum(l.domain[1])} ${esc(l.unit)}${
            l.higher_is === "good" ? " · plus haut, c'est mieux" : l.higher_is === "bad" ? " · plus haut, c'est pire" : ""}${l.source ? " · " + esc(srcName(l.source)) : ""}</span></p></div></div>`).join("")}`;
      }).join("")}`,
    Sources: () => `
      ${h2("pedia", null, "Sources")}
      <p>Chaque fichier téléchargé est cité avec son adresse, sa date de récupération et sa taille ; son empreinte SHA-256
      est dans <code>web/data/sources.json</code>.</p>
      ${data.sources.map((s) => `
        <h4>${esc(s.title)}</h4>
        <p>${esc(s.description)}<br>
        <span class="muted">${esc(s.publisher)} · <b>${esc(s.license)}</b>${s.vintage ? " · " + esc(s.vintage) : ""} ·
        <a href="${esc(s.homepage)}" target="_blank" rel="noopener">site</a></span></p>
        <table>${(s.files || []).map((f) => `<tr><td><code>${esc(f.url)}</code></td><td class="muted" style="white-space:nowrap">${esc((f.retrieved || "").slice(0, 10))}<br>${((f.bytes || 0) / 1e6).toFixed(1)} Mo</td></tr>`).join("")}</table>`).join("")}`,
  };

  const show = (name) => {
    if (!pages[name]) name = "About this map";
    body.innerHTML = pages[name]();
    body.scrollTop = 0;
    nav.querySelectorAll("button").forEach((b) => {
      const on = b.dataset.page === name;
      b.classList.toggle("active", on);
      b.setAttribute("aria-current", on ? "page" : "false");
    });
  };
  nav.innerHTML = `<div class="hd">Almanach</div>` + Object.keys(pages).map((p) => `<button data-page="${esc(p)}">${esc(LABEL[p] || p)}</button>`).join("");
  nav.onclick = (e) => {
    const b = e.target.closest("button[data-page]");
    if (b) show(b.dataset.page);
  };
  const close = () => {
    if (modal.hidden) return;
    modal.hidden = true;
    if (restoreFocus && document.contains(restoreFocus)) restoreFocus.focus();
    restoreFocus = null;
  };
  modal.onclick = (e) => {
    if (e.target === modal || e.target.closest("[data-close]")) close();
  };
  // Keep Tab inside the dialog.
  modal.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    const f = [...card.querySelectorAll("button, a[href], [tabindex]:not([tabindex='-1'])")].filter((x) => x.offsetParent);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  return {
    open(page = "About this map") { // (pages absentes, comme « Yields », retombent sur « About this map »)
      if (modal.hidden) restoreFocus = document.activeElement;
      show(page);
      modal.hidden = false;
      (nav.querySelector("button.active") || card.querySelector("[data-close]"))?.focus();
    },
    close,
    get isOpen() {
      return !modal.hidden;
    },
  };
}
