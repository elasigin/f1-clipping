const d3 = window.d3;
export const metres = (v) => `${d3.format(",.0f")(v)} m`;
export const kmh = (v) => `${d3.format(".0f")(v)} km/h`;
export const signed = (v) => (Math.abs(v) < 0.5 ? "0" : d3.format("+.0f")(v).replace("-", "−"));
export const percent = (v) => d3.format(".1%")(v);
export const lapTime = (t) => `${Math.floor(t / 60)}:${d3.format("06.3f")(t % 60)}`;

// Element builder that only ever sets text, never markup.
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === false || v == null) continue;
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  node.append(...children.filter((c) => c != null));
  return node;
}
