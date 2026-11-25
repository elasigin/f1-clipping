// The opening figures: one straight, annotated, and a schematic of where the power goes.
import { el, metres, kmh } from "../format.js";
import { createTooltip } from "../tooltip.js";

const d3 = window.d3;
const RANGE = [1250, 2260];          // the Kemmel straight, up to the braking point
const M = { top: 30, right: 16, bottom: 66, left: 50 };
const H = 290;

export function createHero(root, cmp) {
  const chart = el("div", { class: "chart" });
  root.append(chart, el("figcaption", {},
    "Speed along the Kemmel straight, Spa, qualifying. Hatching marks the stretches that fit clipping. ",
    "The speed axis starts at 290 km/h. Gaps in the lines are missing telemetry."));
  const svg = d3.select(chart).append("svg").attr("role", "img").attr("aria-label",
    "Line chart of speed along the Kemmel straight. In 2025 speed rises from 309 to 341 km/h. In 2026 it rises to 328, " +
    "then falls to below 300 before braking, at full throttle.");
  const tip = createTooltip(chart);
  const p = svg.append("defs").append("pattern").attr("id", "hero-hatch").attr("width", 7).attr("height", 7)
    .attr("patternUnits", "userSpaceOnUse").attr("patternTransform", "rotate(45)");
  p.append("rect").attr("width", 7).attr("height", 7).attr("fill", "var(--y2026)").attr("fill-opacity", 0.13);
  p.append("line").attr("y2", 7).attr("stroke", "var(--y2026)").attr("stroke-width", 3).attr("stroke-opacity", 0.55);
  const g = svg.append("g");
  const hover = svg.append("g").attr("pointer-events", "none");
  const pts = cmp.s.map((s, i) => ({ s, a: cmp.a.speed[i], b: cmp.b.speed[i], ta: cmp.a.throttle[i], tb: cmp.b.throttle[i] }))
    .filter((d) => d.s >= RANGE[0] && d.s <= RANGE[1]);
  const x = d3.scaleLinear().domain(RANGE), y = d3.scaleLinear([290, 350], [H, 0]);
  let width = 0;

  function draw() {
    width ||= chart.clientWidth;
    if (!width) return;
    const W = width - M.left - M.right, small = width < 600;
    x.range([0, W]);
    svg.attr("viewBox", `0 0 ${width} ${M.top + H + M.bottom}`);
    for (const n of [g, hover]) n.attr("transform", `translate(${M.left},${M.top})`);
    g.selectAll("*").remove();
    for (const t of [290, 300, 310, 320, 330, 340]) {
      g.append("line").attr("x2", W).attr("y1", y(t)).attr("y2", y(t)).attr("stroke", t === 290 ? "var(--rule)" : "var(--grid)");
      g.append("text").attr("x", -8).attr("y", y(t)).attr("dy", "0.32em").attr("text-anchor", "end").text(t);
    }
    g.append("text").attr("class", "strong").attr("x", -M.left + 4).attr("y", -16).text("km/h");
    for (const z of cmp.b.zones) {
      const [s0, s1] = [Math.max(z.s0, RANGE[0]), Math.min(z.s1, RANGE[1])];
      if (s1 <= s0) continue;
      g.append("rect").attr("x", x(s0)).attr("width", x(s1) - x(s0)).attr("height", H).attr("fill", "url(#hero-hatch)");
    }
    const line = (k) => d3.line().defined((d) => d[k] != null).x((d) => x(d.s)).y((d) => y(d[k]))(pts);
    g.append("path").attr("class", "line y2025 thick").attr("d", line("a"));
    g.append("path").attr("class", "line y2026 thick").attr("d", line("b"));

    const peak = d3.greatest(pts.filter((d) => d.b != null), (d) => d.b);
    const last = pts.findLast((d) => d.b != null), top = pts.findLast((d) => d.a != null);
    const note = (px, py, anchor, ...lines) => {
      const t = g.append("text").attr("class", "halo note-text").attr("text-anchor", anchor);
      lines.forEach((s, i) => t.append("tspan").attr("x", px).attr("y", py + i * 17).attr("class", i ? null : "strong").text(s));
    };
    for (const [d, k, yr] of [[peak, "b", 2026], [last, "b", 2026], [top, "a", 2025]]) {
      g.append("circle").attr("class", `dot y${yr}`).attr("r", 5).attr("cx", x(d.s)).attr("cy", y(d[k]));
    }
    note(x(top.s) + 6, y(top.a) - 16, "end", `2025 climbs to ${kmh(top.a)}`);
    if (small) note(x(peak.s) + 8, y(peak.b) - 16, "end", `2026 peak: ${kmh(peak.b)}`);
    else note(x(peak.s) - 6, y(peak.b) - 32, "end", `2026 peaks at ${kmh(peak.b)},`, "then starts to slow");
    note(x(last.s) - 22, y(last.b) - 4, "end", `2026 drops to ${kmh(last.b)}`, small ? "flat out" : "still at full throttle");

    // Both throttles, as one bar, because "full throttle" is the whole point.
    g.append("rect").attr("y", H + 12).attr("width", W).attr("height", 18).attr("rx", 3).attr("fill", "var(--ink)");
    g.append("text").attr("x", W / 2).attr("y", H + 25).attr("text-anchor", "middle").style("fill", "#fff")
      .text(small ? "Full throttle in both seasons" : "Full throttle, no brake, in both seasons");
    for (const t of x.ticks(small ? 4 : 8)) {
      g.append("text").attr("x", x(t)).attr("y", H + 48).attr("text-anchor", "middle").text(d3.format(",")(t));
    }
    g.append("text").attr("x", W).attr("y", H + 64).attr("text-anchor", "end").text("metres into the lap");
  }

  svg.on("pointermove", (e) => {
    const s = x.invert(d3.pointer(e, g.node())[0]);
    hover.selectAll("*").remove();
    if (s < RANGE[0] || s > RANGE[1]) return tip.hide();
    const d = pts[d3.leastIndex(pts, (q) => Math.abs(q.s - s))];
    hover.append("line").attr("class", "crosshair").attr("x1", x(d.s)).attr("x2", x(d.s)).attr("y2", H);
    const row = (yr, v, th) => el("div", { class: "row" }, el("span", { class: "key", style: `border-color:var(--y${yr})` }),
      el("b", {}, v == null ? "no data" : kmh(v)), el("span", {}, `${yr}${v == null ? "" : `, throttle ${th}%`}`));
    tip.show(x(d.s) + M.left, M.top + H - 110, el("div", { class: "where" }, `${metres(d.s)} into the lap`),
      row(2025, d.a, d.ta), row(2026, d.b, d.tb));
  }).on("pointerleave", () => { hover.selectAll("*").remove(); tip.hide(); });

  new ResizeObserver(([entry]) => {
    const w = Math.round(entry.contentRect.width);
    if (w && w !== width) { width = w; draw(); }
  }).observe(chart);
  draw();
}

// Three states of the same straight. Arrow widths are only suggestive.
export function createMechanism(root) {
  const panels = [
    ["Deploying", "The battery adds power through the motor.", [["engine", 16, "e"], ["battery", 14, "m"]]],
    ["Clipping", "The motor stops helping. Only the engine drives.", [["engine", 16, "e"]]],
    ["Super clipping", "The motor takes engine power to charge the battery.", [["engine", 7, "e"], ["charge", 9, "m"]]],
  ];
  const row = el("div", { class: "panels" });
  root.append(row, el("figcaption", {}, "Schematic, not data. The throttle is fully open in all three."));
  for (const [name, text, flows] of panels) {
    const panel = el("div", { class: "panel" }, el("h3", {}, name), el("p", {}, text));
    const svg = d3.select(panel).append("svg").attr("viewBox", "0 0 300 168").attr("role", "img").attr("aria-label", `${name}: ${text}`);
    const box = (x, y, w, h, label) => {
      svg.append("rect").attr("x", x).attr("y", y).attr("width", w).attr("height", h).attr("rx", 7)
        .attr("fill", "#fff").attr("stroke", "var(--ink)").attr("stroke-width", 1.5);
      svg.append("text").attr("class", "strong").attr("x", x + w / 2).attr("y", y + h / 2).attr("dy", "0.35em")
        .attr("text-anchor", "middle").text(label);
    };
    const arrow = (x0, y0, x1, y1, w, kind) => {
      const a = Math.atan2(y1 - y0, x1 - x0), head = w + 5, ex = x1 - Math.cos(a) * head, ey = y1 - Math.sin(a) * head;
      const fill = kind === "m" ? "var(--electric)" : "var(--ink-2)";
      svg.append("line").attr("x1", x0).attr("y1", y0).attr("x2", ex).attr("y2", ey).attr("stroke", fill).attr("stroke-width", w);
      svg.append("path").attr("d", `M0,${-w * 0.5 - 6}L${head},0L0,${w * 0.5 + 6}Z`).attr("fill", fill)
        .attr("transform", `translate(${ex},${ey}) rotate(${(a * 180) / Math.PI})`);
    };
    for (const [kind, w, style] of flows) {
      if (kind === "engine") arrow(92, 34, 206, 34, w, style);
      if (kind === "battery") arrow(92, 136, 206, 136, w, style);
      if (kind === "charge") arrow(46, 58, 46, 110, w, style);
    }
    if (name === "Clipping") svg.append("line").attr("x1", 92).attr("x2", 206).attr("y1", 136).attr("y2", 136)
      .attr("stroke", "var(--rule)").attr("stroke-width", 2).attr("stroke-dasharray", "4 5");
    if (name !== "Super clipping") {
      svg.append("text").attr("x", 149).attr("y", name === "Deploying" ? 116 : 124).attr("text-anchor", "middle")
        .text(name === "Deploying" ? "motor" : "motor: no help");
    }
    if (name === "Super clipping") svg.append("text").attr("x", 62).attr("y", 86).text("through the motor");
    box(2, 12, 88, 44, "Engine"); box(2, 114, 88, 44, "Battery"); box(210, 12, 88, 146, "Wheels");
    row.append(panel);
  }
}
