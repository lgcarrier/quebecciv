// DOM icons: the SVG set from icons.js. An id the set lacks draws an empty box of the same size, never a glyph
// or an emoji, so rows stay aligned.
import { svgIcon, hasIcon } from "../icons.js";

// icon("l-income") → inline <svg> (currentColor). The second argument is kept for call sites that still pass one;
// it is ignored.
export function icon(id, _unused = null, { size = 16, title = "" } = {}) {
  if (id && hasIcon(id)) return svgIcon(id, { size, title });
  return `<span class="icon-blank" aria-hidden="true" style="display:inline-block;width:${size}px;height:${size}px;flex:none"></span>`;
}

// For data objects (yields, lenses, resource types) that carry an SVG id in `icon`.
export function glyph(o, size = 16, title = "") {
  return icon(o?.icon, null, { size, title });
}
