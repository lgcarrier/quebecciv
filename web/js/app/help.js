// Keyboard & mouse cheat-sheet.
import { icon } from "../ui/icon.js";

const isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");
const MOD = isMac ? "⌘" : "Ctrl";

const ROWS = [
  ["Se déplacer", [
    [["Glisser", "←↑→↓", "WASD"], "Déplacer la carte"],
    [["Molette", "+", "–"], "Zoomer et dézoomer"],
    [["Double-clic"], "Zoomer sur un point"],
    [["Deux doigts"], "Pincer pour zoomer, glisser pour se déplacer (tactile)"],
    [["Mini-carte"], "Cliquer ou glisser pour y sauter"],
  ]],
  ["Explorer", [
    [["Clic sur une ville"], "Ouvrir la ville"],
    [["Clic sur la terre"], "Ouvrir la région"],
    [["/", `${MOD} K`], "Chercher un lieu, une ville ou une région"],
    [["L", "Maj L"], "Lentille suivante / précédente"],
    [["Légende"], "Survoler ou glisser sur l'échelle pour ne montrer que cette plage"],
  ]],
  ["Panneaux", [
    [["?"], "Cette aide"],
    [["Échap"], "Fermer l'aide, la recherche, l'Almanach, puis le panneau"],
  ]],
];

export function initHelp() {
  const modal = document.getElementById("help");
  if (!modal) return { open() {}, close() {}, get isOpen() { return false; } };
  const card = modal.querySelector(".help-card");
  let restore = null;
  card.innerHTML = `
    <button class="icon-btn help-close" data-close aria-label="Fermer l'aide">${icon("close", null, { size: 13 })}</button>
    <h2 id="help-title">${icon("help", "?", { size: 22 })}<span>Commandes</span></h2>
    <div class="help-cols">${ROWS.map(([title, rows]) => `
      <section><h3>${title}</h3>${rows.map(([keys, what]) => `
        <div class="help-row"><span class="keys">${keys.map((k) => `<kbd>${k}</kbd>`).join("")}</span><span>${what}</span></div>`).join("")}
      </section>`).join("")}</div>
    <p class="help-foot">Chaque nombre vient de données publiques : l'<b>Almanach</b> cite les sources.
      Le lien dans la barre d'adresse rouvre toujours cette vue exacte.
      Code source : <a href="https://github.com/lgcarrier/quebecciv" target="_blank" rel="noopener">github.com/lgcarrier/quebecciv</a> (MIT).
      D'après <a href="https://github.com/lmveprog/Europe-Civilization" target="_blank" rel="noopener">Europe-Civilization</a> (lmveprog) et
      <a href="https://karpathy.ai/usaciv/" target="_blank" rel="noopener">usaciv</a> d'Andrej Karpathy, licence MIT.</p>`;

  const close = () => {
    if (modal.hidden) return;
    modal.hidden = true;
    if (restore && document.contains(restore)) restore.focus();
    restore = null;
  };
  modal.addEventListener("click", (e) => {
    if (e.target === modal || e.target.closest("[data-close]")) close();
  });
  modal.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    e.preventDefault(); // the only focusable control is the close button
    card.querySelector("[data-close]").focus();
  });

  return {
    open() {
      if (!modal.hidden) return;
      restore = document.activeElement;
      modal.hidden = false;
      card.querySelector("[data-close]").focus();
    },
    close,
    toggle() { modal.hidden ? this.open() : close(); },
    get isOpen() { return !modal.hidden; },
  };
}
