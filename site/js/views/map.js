// View 2: the racing line colored by the 2026 minus 2025 speed difference.
// A section is selected by dragging ALONG the track, so the brush is a distance
// interval, exactly like the trace's.
import { zoneAt } from "../data.js";
import { el, metres, kmh, signed } from "../format.js";
import { createTooltip } from "../tooltip.js";
import { diffColor, smooth, DIFF_LIMIT } from "../scales.js";

const d3 = window.d3;
const ORIGIN = "map";
const PAD = 40;                 // room for corner labels
const REACH = 26;               // px from the track that still counts as on it
const HANDLE = 15;              // px from an end of the selection that grabs it

export function createMap(root, state, { compact = false, maxHeight = 540 } = {}) {
  const title = el("h4", {}, "Where on the track");
  const legend = el("div", { class: "map-legend" });
  const chart = el("div", { class: "chart" });
  const hint = el("p", { class: "hint" }, "Drag along the track to select a section, or drag either end to adjust it.");
  const sections = el("div", { class: "sections", role: "group", "aria-label": "Select a full-throttle section" });
  root.append(...(compact ? [chart] : [title, legend, chart, hint, sections]));

  const svg = d3.select(chart).append("svg").attr("role", "group").attr("aria-roledescription", "track map");
  const tip = createTooltip(chart);
  const layer = Object.fromEntries(["casing", "hit", "track", "marks", "labels", "handles", "hover"]
    .map((k) => [k, svg.append("g").attr("class", k)]));

  let cmp = null, width = 0, height = 0, P = [], diff = [], drag = null;
  // Not drawn yet (hidden, so without a width) counts as not current.
  const current = () => cmp && P.length && cmp.circuit.id === state.get().circuit;
  const idx = (s) => Math.max(0, Math.min(P.length - 1, Math.round(s / cmp.step)));

  // --- geometry ---------------------------------------------------------------------
  function project() {
    const { x, y } = cmp.circuit.ref;
    const r = (cmp.circuit.rotation * Math.PI) / 180, c = Math.cos(r), n = Math.sin(r);
    const pts = x.map((v, i) => [v * c - y[i] * n, -(v * n + y[i] * c)]);   // screen y points down
    const [x0, x1] = d3.extent(pts, (p) => p[0]), [y0, y1] = d3.extent(pts, (p) => p[1]);
    const aspect = (y1 - y0) / (x1 - x0);
    height = Math.round(Math.max(220, Math.min(maxHeight, (width - 2 * PAD) * aspect + 2 * PAD)));
    const k = Math.min((width - 2 * PAD) / (x1 - x0), (height - 2 * PAD) / (y1 - y0));
    const ox = (width - k * (x1 - x0)) / 2, oy = (height - k * (y1 - y0)) / 2;
    P = pts.map((p) => [ox + k * (p[0] - x0), oy + k * (p[1] - y0)]);
  }

  // Unit normal pointing to whichever side has more free space.
  function outward(i, d) {
    const a = P[Math.max(0, i - 4)], b = P[Math.min(P.length - 1, i + 4)];
    const len = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
    const nx = -(b[1] - a[1]) / len, ny = (b[0] - a[0]) / len;
    const room = (sgn) => {
      const q = [P[i][0] + sgn * nx * d, P[i][1] + sgn * ny * d];
      return d3.min(P, (p) => Math.hypot(p[0] - q[0], p[1] - q[1]));
    };
    const sgn = room(1) >= room(-1) ? 1 : -1;
    return [sgn * nx, sgn * ny];
  }

  function nearest(px) {
    const i = d3.minIndex(P, (p) => Math.hypot(p[0] - px[0], p[1] - px[1]));
    return { i, d: Math.hypot(P[i][0] - px[0], P[i][1] - px[1]) };
  }

  // Walk downhill from the last position. The match can slide along the track but
  // cannot jump to another part of it that happens to pass close by.
  function follow(px, from) {
    let i = from;
    for (let step = 0; step < 60; step++) {
      let best = i;
      for (let j = Math.max(0, i - 12); j <= Math.min(P.length - 1, i + 12); j++) {
        if (Math.hypot(P[j][0] - px[0], P[j][1] - px[1]) < Math.hypot(P[best][0] - px[0], P[best][1] - px[1])) best = j;
      }
      if (best === i) break;
      i = best;
    }
    return i;
  }

  const pathOf = (i0, i1) => d3.line()(P.slice(i0, i1 + 1));

  // --- drawing ----------------------------------------------------------------------
  function draw() {
    width ||= chart.clientWidth;        // a hidden tab gets no resize event
    if (!cmp || !width) return;
    project();
    svg.attr("viewBox", `0 0 ${width} ${height}`);
    layer.hit.selectAll("path").data([0]).join("path").attr("class", "hit")
      .attr("d", pathOf(0, P.length - 1)).attr("stroke-width", REACH * 2);

    // Zones get a dark outline, so clipping never depends on color.
    layer.casing.selectAll("path").data(cmp.b?.zones ?? []).join("path").attr("class", "casing")
      .attr("d", (z) => pathOf(idx(z.s0), idx(z.s1)));

    const segs = d3.pairs(d3.range(P.length)).map(([i]) => ({ i, v: segValue(i) }));
    layer.track.selectAll("line").data(segs, (d) => d.i).join("line")
      .attr("x1", (d) => P[d.i][0]).attr("y1", (d) => P[d.i][1])
      .attr("x2", (d) => P[d.i + 1][0]).attr("y2", (d) => P[d.i + 1][1])
      .attr("class", (d) => (d.v == null ? "seg missing" : "seg"))
      .attr("stroke", (d) => (d.v == null ? null : diffColor(d.v)));
    drawLabels();
    drawSelection();
    drawHover();
  }

  const segValue = (i) => (diff[i] == null || diff[i + 1] == null ? null : (diff[i] + diff[i + 1]) / 2);

  function drawLabels() {
    layer.marks.selectAll("*").remove();
    layer.labels.selectAll("*").remove();
    const taken = [];
    const clear = (x, y, w, h = 14) => {
      const hits = taken.some((t) => Math.abs(t.x - x) < (t.w + w) / 2 && Math.abs(t.y - y) < (t.h + h) / 2);
      const onTrack = P.some((p) => Math.abs(p[0] - x) < w / 2 + 3 && Math.abs(p[1] - y) < h / 2 + 3);
      const inside = x - w / 2 >= 0 && x + w / 2 <= width && y - h / 2 >= 0 && y + h / 2 <= height;
      return inside && !hits && !onTrack;
    };
    const put = (i, text, cls, dists) => {
      const t = layer.labels.append("text").attr("class", cls).attr("text-anchor", "middle").attr("dy", "0.34em").text(text);
      const w = t.node().getComputedTextLength();
      for (const d of dists) {
        for (const sgn of [1, -1]) {
          const [nx, ny] = outward(i, d);
          const reach = d + Math.abs(nx) * w / 2;
          const x = P[i][0] + sgn * nx * reach, y = P[i][1] + sgn * ny * d;
          const off = Math.abs(nearest([x, y]).i - i);         // must read as belonging to its own corner
          if (clear(x, y, w) && Math.min(off, P.length - off) <= 20) {
            taken.push({ x, y, w, h: 14 });
            t.attr("x", x).attr("y", y);
            return true;
          }
        }
      }
      t.remove();
      return false;
    };

    // Start line and direction of travel.
    const a = P[0], b = P[6], len = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
    const ux = (b[0] - a[0]) / len, uy = (b[1] - a[1]) / len;
    layer.marks.append("line").attr("class", "start").attr("x1", a[0] - uy * 11).attr("y1", a[1] + ux * 11)
      .attr("x2", a[0] + uy * 11).attr("y2", a[1] - ux * 11);
    const [nx, ny] = outward(8, 16), m = P[8];
    layer.marks.append("path").attr("class", "arrow")
      .attr("d", "M-8,0H6M2,-4L6,0L2,4")
      .attr("transform", `translate(${m[0] + nx * 15},${m[1] + ny * 15}) rotate(${(Math.atan2(uy, ux) * 180) / Math.PI})`);
    taken.push({ x: m[0] + nx * 15, y: m[1] + ny * 15, w: 20, h: 20 });

    const big = d3.greatest(cmp.b?.zones ?? [], (z) => z.drop);
    if (big) put(idx((big.s0 + big.s1) / 2), `−${d3.format(".0f")(big.drop)} km/h`, "halo strong", [18, 24, 32, 42]);
    put(0, "Start", "halo", [20, 28, 36]);
    for (const c of cmp.circuit.corners) put(idx(c.s), `T${c.label}`, "halo", [16, 22, 30]);
  }

  function drawSelection() {
    const b = state.get().brush;
    const inside = (i) => !b || (i * cmp.step >= b[0] && (i + 1) * cmp.step <= b[1]);
    layer.track.selectAll("line").classed("faded", (d) => !inside(d.i)).classed("chosen", (d) => b && inside(d.i));
    layer.casing.selectAll("path").classed("faded", (z) => b && (z.s1 <= b[0] || z.s0 >= b[1]));

    const ends = b ? [0, 1].map((k) => ({ k, s: b[k] })) : [];
    layer.handles.selectAll("circle").data(ends, (d) => d.k).join("circle")
      .attr("class", "end-handle").attr("r", 7).attr("tabindex", 0).attr("role", "slider")
      .attr("cx", (d) => P[idx(d.s)][0]).attr("cy", (d) => P[idx(d.s)][1])
      .attr("aria-label", (d) => (d.k ? "End of section" : "Start of section"))
      .attr("aria-valuemin", 0).attr("aria-valuemax", cmp.length)
      .attr("aria-valuenow", (d) => d.s).attr("aria-valuetext", (d) => metres(d.s))
      .on("keydown", nudge);
  }

  function nudge(e, d) {
    const dir = { ArrowRight: 1, ArrowUp: 1, ArrowLeft: -1, ArrowDown: -1 }[e.key];
    if (!dir) return;
    e.preventDefault();
    const b = [...state.get().brush];
    b[d.k] = Math.max(0, Math.min(cmp.length, b[d.k] + dir * cmp.step * (e.shiftKey ? 10 : 2)));
    if (b[1] - b[0] >= cmp.step) state.set({ brush: b, hover: b[d.k] }, "map-key");
  }

  function drawHover(origin) {
    layer.hover.selectAll("*").remove();
    const s = current() ? state.get().hover : null;
    if (s == null) return tip.hide();
    const i = idx(s), [x, y] = P[i];
    layer.hover.append("circle").attr("class", "cursor").attr("r", 7).attr("cx", x).attr("cy", y);
    if (origin !== ORIGIN || drag) return tip.hide();      // the view under the pointer explains itself
    const row = (yr, lap) => lap && el("div", { class: "row" },
      el("span", { class: "key", style: `border-color:var(--y${yr})` }),
      el("b", {}, lap.speed[i] == null ? "no data" : kmh(lap.speed[i])), el("span", {}, `${yr} ${lap.driver}`));
    const d = cmp.diff[i], z = zoneAt(cmp.b, s);
    // Docked at the far edge, so it never covers the part being pointed at.
    tip.show(x < width / 2 ? width : -16, y < height / 2 ? "bottom" : 0, el("div", { class: "where" }, `${metres(s)} into the lap`), row(2025, cmp.a), row(2026, cmp.b),
      d == null ? null : el("div", { class: "row" }, el("span", { class: "key", style: "border-color:transparent" }),
        el("b", {}, `${signed(d)} km/h`), el("span", {}, "2026 vs 2025")),
      z && el("div", { class: "zone-note" }, `Inferred clipping: −${d3.format(".0f")(z.drop)} km/h over ${metres(z.s1 - z.s0)}`));
  }

  // --- dragging along the track -------------------------------------------------------
  const at = (e) => d3.pointer(e, svg.node());

  svg.on("pointerdown", (e) => {
    if (!current() || e.button) return;
    const px = at(e), b = state.get().brush;
    const grabbed = b && [0, 1].find((k) => Math.hypot(P[idx(b[k])][0] - px[0], P[idx(b[k])][1] - px[1]) < HANDLE);
    const n = nearest(px);
    if (grabbed == null && n.d > REACH) {
      if (b) state.set({ brush: null }, ORIGIN);            // empty space clears, as in the trace
      return;
    }
    e.preventDefault();
    try { svg.node().setPointerCapture(e.pointerId); } catch { /* pointer already gone */ }
    drag = grabbed != null ? { anchor: idx(b[1 - grabbed]), i: idx(b[grabbed]), moved: true, px }
      : { anchor: n.i, i: n.i, moved: false, px };
  }).on("pointermove", (e) => {
    if (!current()) return;
    const px = at(e);
    if (!drag) {
      const n = nearest(px);
      return state.set({ hover: n.d <= REACH ? n.i * cmp.step : null }, ORIGIN);
    }
    if (!drag.moved && Math.hypot(px[0] - drag.px[0], px[1] - drag.px[1]) < 4) return;
    drag.moved = true;
    drag.i = follow(px, drag.i);
    const [i0, i1] = d3.extent([drag.anchor, drag.i]);
    if (i1 > i0) state.set({ brush: [i0 * cmp.step, i1 * cmp.step], hover: drag.i * cmp.step }, ORIGIN);
  }).on("pointerup pointercancel", (e) => {
    if (!drag) return;
    const was = drag;
    drag = null;
    if (!was.moved && e.type === "pointerup") {              // a click: pick the zone under it, or clear
      const z = zoneAt(cmp.b, was.i * cmp.step);
      state.set({ brush: z ? [z.s0, z.s1] : null }, ORIGIN);
    }
    drawHover(ORIGIN);
  }).on("pointerleave", () => { if (!drag) state.set({ hover: null }, ORIGIN); })
    .on("keydown", (e) => { if (e.key === "Escape") state.set({ brush: null, hover: null }, "map-key"); });

  // --- text ---------------------------------------------------------------------------------
  function drawText() {
    const { meta, circuit } = cmp;
    svg.attr("aria-label", `Track map of ${meta.name}. Colored by speed difference: blue where 2025 is faster, orange where 2026 is faster. ` +
      `${cmp.b?.zones.length ?? 0} inferred clipping zones are outlined.`);
    const stops = d3.range(0, 1.01, 0.1).map((t) => diffColor(-DIFF_LIMIT + t * 2 * DIFF_LIMIT));
    legend.replaceChildren(
      ...(cmp.a && cmp.b ? [el("div", { class: "ramp-row" }, el("span", {}, `2025 faster by ${DIFF_LIMIT}+`),
        el("span", { class: "ramp", style: `background:linear-gradient(to right,${stops.join(",")})` }),
        el("span", {}, `2026 faster by ${DIFF_LIMIT}+ km/h`))] : [el("div", {}, "No comparison lap, so the track is not colored.")]),
      el("div", { class: "keys" },
        ...(cmp.b?.zones.length ? [el("span", { class: "key-item" }, el("span", { class: "k-zone" }), "2026 inferred clipping")] : []),
        el("span", { class: "key-item" }, el("span", { class: "k-missing" }), cmp.a && cmp.b ? "no usable telemetry" : "no comparison")));
    sections.replaceChildren(...circuit.segments.map((g) => el("button", {
      type: "button", "data-s0": g.s0, "data-s1": g.s1,
      onclick: () => state.set({ brush: pressed(g) ? null : [g.s0, g.s1] }, "section"),
    }, g.name)));
    drawPressed();
  }

  const pressed = (g) => { const b = state.get().brush; return Boolean(b && b[0] === g.s0 && b[1] === g.s1); };
  function drawPressed() {
    for (const n of sections.children) n.setAttribute("aria-pressed", pressed({ s0: +n.dataset.s0, s1: +n.dataset.s1 }));
  }

  // --- wiring ---------------------------------------------------------------------------------
  state.on("brush", ORIGIN, () => { if (current()) { drawSelection(); drawPressed(); } });
  state.on("hover", ORIGIN, ({ origin }) => { if (current()) drawHover(origin); });

  const ro = new ResizeObserver(([entry]) => {
    const w = Math.round(entry.contentRect.width);
    if (w && w !== width) { width = w; draw(); }
  });
  ro.observe(chart);

  return {
    update(next) { cmp = next; drag = null; diff = smooth(cmp.diff); drawText(); draw(); },
    resize: draw,
    destroy() { ro.disconnect(); root.replaceChildren(); },
  };
}
