// Places: every municipality, town and village of the map (about 126,000), named on the map as you zoom in.
// The biggest come first; smaller ones appear zoom step by zoom step until, close in, every village has its name.
// Names never overlap one another and step aside for the city hexes (their banners carry the city's name).
// Hover: population and country; click: the place's card. Toggle: "Places" in the map layers menu.
// Data: placenames/top.json (places of top_min people or more) once the map is zoomed in, then the
// placenames/t<col>_<row>.json tiles of smaller places on screen, only when zoomed in far enough to name them.
import { esc, int } from "../../format.js";

// Smallest population named at each hex size (hex radius in css px), and the name's size.
const TIERS = [
  { rpx: 14, min: 60000 }, { rpx: 20, min: 25000 }, { rpx: 28, min: 10000 }, { rpx: 40, min: 4000 },
  { rpx: 58, min: 1500 }, { rpx: 85, min: 500 }, { rpx: 120, min: 0 },
];
const FONT = '"Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif';
const CODE = 0, NAME = 1, DEP = 2, POP = 3, X = 4, Y = 5; // placenames columns
const LIMIT = 900; // names per render: plenty for a screen, cheap to draw

const minPopFor = (Rpx) => {
  let min = Infinity;
  for (const t of TIERS) if (Rpx >= t.rpx) min = t.min;
  return min;
};
// The map shows the bare name; the homonym hint ("Aalst (Aalst)", "Buchs (AG)") stays in the tooltip.
const label = (name) => String(name).replace(/\s*\([^)]*\)$/, "");
const sizeFor = (pop) => (pop >= 100000 ? 13 : pop >= 20000 ? 12 : pop >= 5000 ? 11 : 10);

export function install(app) {
  let top = null, loading = false, version = 0, on = true;
  let tileKeys = new Set(); // tiles that exist
  const tileState = new Map(); // tile key → "loading" | "done"
  const chunks = []; // {rows, x0, y0, x1, y1}: top.json (unbounded) and the loaded tiles
  let drawn = []; // the labels of the last render: {r, x0, y0, x1, y1} in map units, for hover and click

  function loadTop() {
    if (top || loading) return;
    loading = true;
    app.loadData("placenames/top").then((d) => {
      loading = false;
      if (!d?.rows) return;
      top = d;
      tileKeys = new Set(d.tiles || []);
      chunks.push({ rows: d.rows, x0: -Infinity, y0: -Infinity, x1: Infinity, y1: Infinity });
      version++;
      app.requestDraw();
    }, () => { loading = false; });
  }

  // Load the tiles of small places that cover the view (and a margin), once each.
  function loadTiles(x0, y0, x1, y1) {
    const T = top.tile;
    for (let tx = Math.floor(x0 / T); tx <= Math.floor(x1 / T); tx++) {
      for (let ty = Math.floor(y0 / T); ty <= Math.floor(y1 / T); ty++) {
        const key = `${tx}_${ty}`;
        if (!tileKeys.has(key) || tileState.has(key)) continue;
        tileState.set(key, "loading");
        app.loadData(`placenames/t${key}`).then((d) => {
          tileState.set(key, "done");
          if (d?.rows) chunks.push({ rows: d.rows, x0: tx * T, y0: ty * T, x1: (tx + 1) * T, y1: (ty + 1) * T });
          version++;
          app.requestDraw();
        }, () => tileState.set(key, "done"));
      }
    }
  }

  const layer = {
    id: "places", z: 88, minRpx: TIERS[0].rpx,
    visible() {
      if (!on || app.mode === "challenge") return false; // the daily challenge asks where places are: no names
      if (!top) { loadTop(); return false; }
      return true;
    },
    sig: () => `p${version}`,
    draw(ctx, vp, w, o) {
      const s = o.s, minPop = minPopFor(o.Rpx);
      const vx0 = vp.x0, vy0 = vp.y0, vx1 = vp.x0 + vp.cssW / s, vy1 = vp.y0 + vp.cssH / s;
      const mx = 50 / s, my = 20 / s;
      if (minPop < top.top_min) loadTiles(vx0 - mx, vy0 - my, vx1 + mx, vy1 + my);
      const cityCells = w.cityByCell;
      const cityNames = new Set([...cityCells.values()].map((c) => label(c.name).toLowerCase()));
      // candidates in view, most populous first
      const cand = [];
      for (const ch of chunks) {
        if (ch.x1 < vx0 - mx || ch.x0 > vx1 + mx || ch.y1 < vy0 - my || ch.y0 > vy1 + my) continue;
        for (const r of ch.rows) {
          if (r[POP] < minPop) break; // rows are sorted by population
          if (r[X] < vx0 - mx || r[X] > vx1 + mx || r[Y] < vy0 - my || r[Y] > vy1 + my) continue;
          if (cityNames.has(label(r[NAME]).toLowerCase())) continue; // the city banner names it already
          cand.push(r);
        }
      }
      cand.sort((a, b) => b[POP] - a[POP]);
      o.screen();
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.lineJoin = "round";
      const boxes = [];
      // city hexes are taken (their banners sit there)
      const R = w.grid.R * s;
      for (const cell of o.cells) {
        if (!cityCells.has(cell)) continue;
        const [sx, sy] = o.toScreen(w.grid.cx(cell), w.grid.cy(cell));
        boxes.push([sx - R, sy - R * 0.9, sx + R, sy + R * 0.9]);
      }
      const overlaps = (b) => boxes.some((p) => b[0] < p[2] && p[0] < b[2] && b[1] < p[3] && p[1] < b[3]);
      drawn = [];
      for (const r of cand) {
        if (drawn.length >= LIMIT) break;
        const pop = r[POP];
        const [sx, sy] = o.toScreen(r[X], r[Y]);
        const px = sizeFor(pop);
        ctx.font = `${pop >= 20000 ? "600 " : ""}${px}px ${FONT}`;
        const name = label(r[NAME]);
        const tw = ctx.measureText(name).width;
        const box = [sx - 4, sy - px * 0.62, sx + 6 + tw + 2, sy + px * 0.62];
        if (overlaps(box)) continue;
        boxes.push(box);
        // dot
        ctx.beginPath();
        ctx.arc(sx, sy, pop >= 20000 ? 2.6 : 2, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(255,246,222,.92)";
        ctx.strokeStyle = "rgba(25,18,10,.75)";
        ctx.lineWidth = 1.2;
        ctx.fill();
        ctx.stroke();
        // name
        ctx.lineWidth = 2.6;
        ctx.strokeStyle = "rgba(20,14,8,.62)";
        ctx.fillStyle = pop >= 20000 ? "rgba(255,244,214,.96)" : "rgba(244,236,214,.9)";
        ctx.strokeText(name, sx + 5, sy);
        ctx.fillText(name, sx + 5, sy);
        drawn.push({ r, x0: vx0 + box[0] / s, y0: vy0 + box[1] / s, x1: vx0 + box[2] / s, y1: vy0 + box[3] / s });
      }
    },
    hit(x, y) {
      for (const d of drawn) if (x >= d.x0 && x <= d.x1 && y >= d.y0 && y <= d.y1) return d.r;
      return null;
    },
    tooltip(r) {
      const region = app.data.states?.find((s) => s.abbr === r[DEP])?.name || r[DEP];
      return `<b>${esc(r[NAME])}</b><br><span class="muted">${esc(region)}${r[POP] ? ` · ${int(r[POP])} hab.` : ""}</span><br><span class="muted">Cliquer pour sa fiche</span>`;
    },
    click(r) {
      app.showPlace?.(r[CODE], { fly: false });
      return true;
    },
  };
  app.registerStaticLayer(layer);
  app.ui.addMapToggle?.({
    id: "places", label: "Lieux", icon: "l-home", title: "Noms des municipalités, de plus en plus en zoomant", default: true,
    get: () => on,
    set: (v) => { on = !!v; app.requestDraw(); },
  });
}
