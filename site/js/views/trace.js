// View 1: speed, speed difference and throttle against distance, 2025 vs 2026.
import { zoneAt, summarize } from "../data.js";
import { el, metres, kmh, signed, percent, lapTime } from "../format.js";
import { createTooltip } from "../tooltip.js";

const d3 = window.d3;
const ORIGIN = "trace";
const M = { top: 24, right: 14, bottom: 40, left: 54 };
const FULL = { speed: { y: 0, h: 290 }, diff: { y: 322, h: 92 }, throttle: { y: 440, h: 58 } };
const COMPACT = { speed: { y: 0, h: 210 }, diff: { y: 240, h: 66 }, throttle: { y: 330, h: 30 } };
const SPEED_DOMAIN = [40, 385];         // room above 350 for zone labels
const SEASONS = [[2025, "a"], [2026, "b"]];

// `compact` is the story's version: shorter, without the controls and the table.
// `uid` keeps SVG ids unique when the page holds two traces.
export function createTrace(root, head, state, { compact = false, uid = "trace" } = {}) {
  const LANES = compact ? COMPACT : FULL;
  const PLOT_H = LANES.throttle.y + LANES.throttle.h;
  const hatch = (season) => `url(#${uid}-hatch-${season})`;
  const title = el("h3", { id: `${uid}-title` });
  const sub = el("p", { class: "sub" });
  const note = el("p", { class: "note" });
  const legend = el("ul", { class: "legend" });
  const chart = el("div", { class: "chart" });
  const readout = el("div", { class: "readout" });
  const hint = el("p", { class: "hint" },
    "Drag across the chart to select a section, or click a hatched zone. Keyboard: arrow keys move, " +
    "Shift+arrow selects, Esc clears.");
  const tbody = el("tbody");
  const table = el("details", {}, el("summary", {}, "Clipping zones as a table"),
    el("div", { class: "table-wrap" }, el("table", {},
      el("thead", {}, el("tr", {}, ...["Lap", "From", "To", "Length", "Speed lost", "Time", ""].map((h) =>
        el("th", { scope: "col" }, h)))), tbody)));
  const live = el("p", { class: "sr", "aria-live": "polite", style: "position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)" });
  head?.append(title, sub, note);
  root.append(...(compact ? [legend, chart, readout, live] : [legend, chart, readout, hint, table, live]));

  const svg = d3.select(chart).append("svg")
    .attr("tabindex", 0).attr("role", "group").attr("aria-roledescription", "chart");
  const tip = createTooltip(chart);

  // Hatching makes clipping readable without color; the two seasons lean opposite ways.
  const defs = svg.append("defs");
  for (const [season, angle] of [[2026, 45], [2025, -45]]) {
    const p = defs.append("pattern").attr("id", `${uid}-hatch-${season}`).attr("width", 7).attr("height", 7)
      .attr("patternUnits", "userSpaceOnUse").attr("patternTransform", `rotate(${angle})`);
    p.append("rect").attr("width", 7).attr("height", 7).attr("fill", `var(--y${season})`).attr("fill-opacity", 0.13);
    p.append("line").attr("y2", 7).attr("stroke", `var(--y${season})`).attr("stroke-width", 3).attr("stroke-opacity", 0.55);
  }
  defs.append("clipPath").attr("id", `${uid}-clip`).append("rect");

  const g = svg.append("g").attr("transform", `translate(${M.left},${M.top})`);
  const layer = Object.fromEntries(["grid", "corners", "zones", "areas", "lines", "labels", "axes", "brush", "hover"]
    .map((k) => [k, g.append("g").attr("class", k)]));

  let cmp = null, width = 0, anchor = null;
  const x = d3.scaleLinear();
  const y = {
    speed: d3.scaleLinear(SPEED_DOMAIN, [LANES.speed.y + LANES.speed.h, LANES.speed.y]),
    diff: d3.scaleLinear([-60, 60], [LANES.diff.y + LANES.diff.h, LANES.diff.y]).clamp(true),
    throttle: d3.scaleLinear([0, 100], [LANES.throttle.y + LANES.throttle.h, LANES.throttle.y]),
  };
  const brush = d3.brushX().on("brush end", brushed);
  const plotW = () => Math.max(10, width - M.left - M.right);
  const current = () => cmp && cmp.circuit.id === state.get().circuit;

  // --- drawing ------------------------------------------------------------------
  function draw() {
    width ||= chart.clientWidth;        // a hidden tab gets no resize event
    if (!cmp || !width) return;
    const W = plotW(), zoom = state.get().zoom;
    x.domain(zoom ?? [0, cmp.length]).range([0, W]);
    y.speed.domain(speedDomain(zoom));
    svg.attr("viewBox", `0 0 ${width} ${M.top + PLOT_H + M.bottom}`);
    defs.select(`#${uid}-clip rect`).attr("y", -2).attr("width", W).attr("height", PLOT_H + 4);
    for (const k of ["zones", "areas", "lines"]) layer[k].attr("clip-path", `url(#${uid}-clip)`);
    drawAxes(W);
    drawZones(W);
    drawSeries();
    brush.extent([[0, 0], [W, PLOT_H]]);
    layer.brush.call(brush);
    layer.brush.selectAll(".overlay").attr("cursor", "crosshair");
    syncBrush();
    drawHover();
  }

  // The story zooms in on slowing of a few km/h, too little to see on the full axis.
  function speedDomain(zoom) {
    if (!compact || !zoom) return SPEED_DOMAIN;
    const seen = cmp.s.flatMap((s, i) => (s < zoom[0] || s > zoom[1] ? [] : [cmp.a?.speed[i], cmp.b?.speed[i]])).filter((v) => v != null);
    const [lo, hi] = d3.extent(seen);
    const span = Math.max(30, hi - lo);
    return [lo - 0.08 * span, hi + 0.25 * span];
  }

  function drawAxes(W) {
    layer.grid.selectAll("*").remove();
    layer.axes.selectAll("*").remove();
    const lanes = [["speed", y.speed.ticks(6).filter((v) => v <= 350), "Speed (km/h)"],
      ["diff", [-40, 0, 40], "2026 minus 2025 (km/h)"], ["throttle", [0, 100], "Throttle (%)"]];
    for (const [k, ticks, label] of lanes) {
      layer.grid.append("g").selectAll("line").data(ticks).join("line")
        .attr("x2", W).attr("y1", y[k]).attr("y2", y[k])
        .attr("stroke", (d) => (k === "diff" && d === 0 ? "var(--rule)" : "var(--grid)"));
      layer.axes.append("g").selectAll("text").data(ticks).join("text")
        .attr("x", -8).attr("y", y[k]).attr("dy", "0.32em").attr("text-anchor", "end")
        .text((d) => (k === "diff" ? (d ? signed(d) : "0") : d));
      layer.axes.append("text").attr("class", "lane-label halo strong").attr("x", 4)
        .attr("y", LANES[k].y + (k === "speed" ? 12 : -7)).text(label);
    }
    layer.axes.append("text").attr("class", "lane-label halo").attr("x", W).attr("y", LANES.diff.y + 10)
      .attr("text-anchor", "end").text("2026 faster ↑");
    layer.axes.append("text").attr("class", "lane-label halo").attr("x", W).attr("y", LANES.diff.y + LANES.diff.h - 3)
      .attr("text-anchor", "end").text("2025 faster ↓");

    const ax = layer.axes.append("g").attr("class", "axis").attr("transform", `translate(0,${PLOT_H})`)
      .call(d3.axisBottom(x).ticks(Math.max(3, Math.round(W / 110))).tickFormat((d) => d3.format(",")(d)));
    ax.selectAll("text").attr("dy", "0.9em").style("font-size", "12px");
    layer.axes.append("text").attr("x", W / 2).attr("y", PLOT_H + 36).attr("text-anchor", "middle")
      .text("Distance along the lap (m)");

    // Corner numbers, dropping any that would touch the previous one.
    let last = -Infinity;
    const shown = cmp.circuit.corners.filter((c) => c.s >= x.domain()[0] && c.s <= x.domain()[1]).map((c) => {
      const px = x(c.s), keep = px - last > 28;
      if (keep) last = px;
      return { ...c, px, keep };
    });
    const c = layer.corners.selectAll("g").data(shown, (d) => d.label).join((e) => {
      const n = e.append("g").attr("class", "corner");
      n.append("line"); n.append("text").attr("text-anchor", "middle").attr("y", -8);
      return n;
    }).attr("transform", (d) => `translate(${d.px},0)`);
    c.select("line").attr("y2", PLOT_H);
    c.select("text").text((d) => (d.keep ? `T${d.label}` : ""));
  }

  function drawZones(W) {
    const zones = SEASONS.flatMap(([season, k]) => (cmp[k]?.zones ?? []).map((z) => ({ ...z, season })));
    const biggest = d3.greatest(zones.filter((z) => z.season === 2026), (z) => z.drop);
    const describe = (z) => `${z.season} clipping zone, ${metres(z.s0)} to ${metres(z.s1)}: loses ${kmh(z.drop)} ` +
      `in ${z.sec} s at full throttle. Press Enter to select.`;
    layer.zones.selectAll("rect.wash").data(zones).join("rect").attr("class", "wash")
      .attr("x", (z) => x(z.s0)).attr("width", (z) => Math.max(1, x(z.s1) - x(z.s0)))
      .attr("y", LANES.diff.y).attr("height", PLOT_H - LANES.diff.y)
      .attr("fill", (z) => `var(--y${z.season})`).attr("fill-opacity", 0.1);
    layer.zones.selectAll("rect.zone").data(zones).join("rect").attr("class", "zone")
      .attr("x", (z) => x(z.s0)).attr("width", (z) => Math.max(1, x(z.s1) - x(z.s0)))
      .attr("y", LANES.speed.y).attr("height", LANES.speed.h)
      .attr("fill", (z) => hatch(z.season))
      .attr("tabindex", 0).attr("role", "button").attr("aria-label", describe)
      .on("keydown", (e, z) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault(); e.stopPropagation();
          state.set({ brush: [z.s0, z.s1] }, "zone");
        }
      });

    // Largest first; a label is dropped rather than allowed to overlap another.
    const placed = [];
    layer.labels.selectAll("*").remove();
    for (const z of d3.sort(zones, (z) => -z.drop)) {
      const full = z === biggest && W > 480;
      const text = full ? `−${d3.format(".0f")(z.drop)} km/h over ${metres(z.s1 - z.s0)} at full throttle`
        : `−${d3.format(".0f")(z.drop)} km/h`;
      const mid = (x(z.s0) + x(z.s1)) / 2;
      if (mid < 0 || mid > W) continue;
      const t = layer.labels.append("text").attr("class", full ? "halo strong" : "halo")
        .attr("y", LANES.speed.y + 14).attr("text-anchor", "middle").text(text);
      const w = t.node().getComputedTextLength();
      // Start clear of the lane's own label in the top-left corner.
      const cx = Math.min(W - w / 2, Math.max(w / 2 + 96, mid));
      if (placed.some((p) => Math.abs(p.cx - cx) < (p.w + w) / 2 + 12)) { t.remove(); continue; }
      t.attr("x", cx);
      placed.push({ cx, w });
    }
  }

  function drawSeries() {
    const pts = (arr) => cmp.s.map((s, i) => [s, arr ? arr[i] : null]);
    const line = (k) => d3.line().defined((d) => d[1] != null).x((d) => x(d[0])).y((d) => y[k](d[1]));
    const series = SEASONS.filter(([, k]) => cmp[k]).flatMap(([season, k]) => [
      { id: `speed-${season}`, cls: `line y${season}`, d: line("speed")(pts(cmp[k].speed)) },
      { id: `thr-${season}`, cls: `line thin y${season}`, d: line("throttle")(pts(cmp[k].throttle)) }]);
    layer.lines.selectAll("path").data(series, (d) => d.id).join("path")
      .attr("class", (d) => d.cls).attr("d", (d) => d.d);

    const area = (sign) => d3.area().defined((d) => d[1] != null).x((d) => x(d[0])).y0(y.diff(0))
      .y1((d) => y.diff(sign * Math.max(0, sign * d[1])));
    layer.areas.selectAll("path").data(cmp.a && cmp.b ? [["faster", 1], ["slower", -1]] : []).join("path")
      .attr("class", (d) => `area ${d[0]}`).attr("d", (d) => area(d[1])(pts(cmp.diff)));
    layer.areas.selectAll("text").data(cmp.a && cmp.b ? [] : [0]).join("text").attr("x", plotW() / 2)
      .attr("y", y.diff(0) - 8).attr("text-anchor", "middle").text("No comparison lap");
  }

  // --- brushing --------------------------------------------------------------------
  const snap = (s) => Math.max(0, Math.min(cmp.length, Math.round(s / cmp.step) * cmp.step));

  function brushed(event) {
    if (!event.sourceEvent || !cmp) return;        // programmatic moves are not user input
    if (event.selection) {
      const [s0, s1] = event.selection.map((px) => snap(x.invert(px)));
      if (s1 > s0) state.set({ brush: [s0, s1] }, ORIGIN);
      if (event.type === "end") syncBrush();        // settle on the grid
    } else if (event.type === "end") {
      const s = x.invert(d3.pointer(event.sourceEvent, g.node())[0]);
      const z = zoneAt(cmp.b, s) ?? zoneAt(cmp.a, s);
      state.set({ brush: z ? [z.s0, z.s1] : null }, "click");
      syncBrush();
    }
  }

  function syncBrush() {
    const b = state.get().brush, [d0, d1] = x.domain();
    const s0 = b && Math.max(b[0], d0), s1 = b && Math.min(b[1], d1);
    // A selection filling the whole zoomed view would only grey it out.
    const show = b && s1 > s0 && s1 - s0 < 0.98 * (d1 - d0);
    layer.brush.call(brush.move, show ? [x(s0), x(s1)] : null);
  }

  // --- hover -------------------------------------------------------------------------
  function drawHover(origin = ORIGIN) {
    const s = current() ? state.get().hover : null;
    const [d0, d1] = x.domain();
    layer.hover.selectAll("*").remove();
    if (s == null || s < d0 || s > d1) return tip.hide();
    const i = Math.max(0, Math.min(cmp.s.length - 1, Math.round(s / cmp.step)));
    const px = x(cmp.s[i]);
    layer.hover.append("line").attr("class", "crosshair").attr("x1", px).attr("x2", px).attr("y2", PLOT_H);
    const rows = SEASONS.filter(([, k]) => cmp[k]).map(([season, k]) => {
      const v = cmp[k].speed[i], th = cmp[k].throttle[i];
      if (v != null) {
        layer.hover.append("circle").attr("class", `dot y${season}`).attr("r", 5).attr("cx", px).attr("cy", y.speed(v));
      }
      return el("div", { class: "row" },
        el("span", { class: "key", style: `border-color:var(--y${season})` }),
        el("b", {}, v == null ? "no data" : kmh(v)),
        el("span", {}, `${season} ${cmp[k].driver}${v == null ? "" : `, throttle ${th}%`}`));
    });
    // When the map is under the pointer its own tooltip explains; here only the crosshair shows.
    if (origin === "map" || origin === "map-key") return tip.hide();
    const d = cmp.diff[i];
    const z26 = zoneAt(cmp.b, cmp.s[i]), z25 = zoneAt(cmp.a, cmp.s[i]);
    const zone = (z, yr) => z && el("div", { class: "zone-note" },
      `Inferred clipping, ${yr}: ${kmh(z.v0)} to ${kmh(z.v1)} over ${metres(z.s1 - z.s0)}` +
      (z.tow ? " (another car within 100 m)" : ""));
    tip.show(px * scale() + M.left * scale(), M.top * scale() + 8,
      el("div", { class: "where" }, `${metres(cmp.s[i])} into the lap`), ...rows,
      d == null ? null : el("div", { class: "row" }, el("span", { class: "key", style: "border-color:transparent" }),
        el("b", {}, `${signed(d)} km/h`), el("span", {}, "2026 vs 2025")),
      zone(z26, 2026), zone(z25, 2025));
  }
  const scale = () => (svg.node().clientWidth || width) / width;

  svg.on("pointermove", (e) => {
    if (!cmp) return;
    const px = d3.pointer(e, g.node())[0];
    state.set({ hover: px < 0 || px > plotW() ? null : snap(x.invert(px)) }, ORIGIN);
  }).on("pointerleave", () => state.set({ hover: null }, ORIGIN));

  svg.on("keydown", (e) => {
    if (!cmp) return;
    if (e.key === "Escape") { anchor = null; state.set({ brush: null, hover: null, zoom: null }, "key"); return; }
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const [d0, d1] = x.domain();
    const from = state.get().hover ?? snap(d0);
    const to = Math.max(d0, Math.min(d1, snap(from + (e.key === "ArrowRight" ? 1 : -1) * cmp.step * 2)));
    if (e.shiftKey) {
      anchor ??= from;
      if (anchor !== to) state.set({ brush: [Math.min(anchor, to), Math.max(anchor, to)] }, "key");
    } else anchor = null;
    state.set({ hover: to }, "key");
    const i = Math.round(to / cmp.step);
    live.textContent = `${metres(to)}. ` + SEASONS.filter(([, k]) => cmp[k]).map(([yr, k]) =>
      `${yr}: ${cmp[k].speed[i] == null ? "no data" : kmh(cmp[k].speed[i])}`).join(", ");
  });

  // --- text around the chart ------------------------------------------------------------
  function drawText() {
    const { a, b, meta, pair } = cmp;
    title.textContent = meta.name;
    const who = (l) => `${l.season} ${l.driver} (${l.teamName}) ${lapTime(l.time)}`;
    const share = (l) => (l.metrics.clipM ? `${percent(l.metrics.share)} of full-throttle distance (${metres(l.metrics.clipM)})` : "none detected");
    sub.textContent = [a, b].filter(Boolean).map(who).join("  vs  ") + ". Inferred clipping: " +
      [b, a].filter(Boolean).map((l) => `${l.season} ${share(l)}`).join("; ") + ".";

    const notes = [pair.note, meta.reason];
    for (const l of [a, b]) {
      if (!l) continue;
      if (l.status === "replaced") {
        notes.push(`${l.season}: the team's best lap (${l.teamBest.driver} ${lapTime(l.teamBest.time)}) has broken telemetry, so a lap ${percent(l.time / l.teamBest.time - 1)} slower is shown.`);
      } else if (l.status === "masked") notes.push(`${l.season}: parts of this lap have no usable telemetry and are left blank.`);
      if (pair.id === "fastest" && l.sessionBest && l.sessionBest.time < l.time - 1e-6) {
        notes.push(`${l.season}: the session's fastest lap was ${l.sessionBest.driver} ${lapTime(l.sessionBest.time)}, but its telemetry is broken.`);
      }
    }
    note.textContent = notes.filter(Boolean).join(" ");

    const swatch = (inner) => { const n = document.createElementNS("http://www.w3.org/2000/svg", "svg"); n.setAttribute("width", 26); n.setAttribute("height", 14); inner(d3.select(n)); return n; };
    const lineKey = (yr) => swatch((n) => n.append("line").attr("class", `line y${yr}`).attr("x1", 2).attr("x2", 24).attr("y1", 7).attr("y2", 7));
    const hatchKey = (yr) => swatch((n) => n.append("rect").attr("width", 26).attr("height", 14).attr("fill", hatch(yr)));
    legend.replaceChildren(...SEASONS.filter(([, k]) => cmp[k]).map(([yr, k]) => el("li", {}, lineKey(yr), `${yr} ${cmp[k].driver}`)),
      ...SEASONS.filter(([, k]) => cmp[k]?.zones.length).reverse().map(([yr]) => el("li", {}, hatchKey(yr), `${yr} inferred clipping`)),
      el("li", {}, "Gap in a line: no usable telemetry"));

    const rows = SEASONS.flatMap(([yr, k]) => (cmp[k]?.zones ?? []).map((z) => el("tr", {},
      el("td", {}, `${yr} ${cmp[k].driver}`), ...[metres(z.s0), metres(z.s1), metres(z.s1 - z.s0), kmh(z.drop), `${z.sec} s`].map((t) => el("td", {}, t)),
      el("td", {}, el("button", { type: "button", onclick: () => state.set({ brush: [z.s0, z.s1] }, "table") }, "Select")))));
    tbody.replaceChildren(...(rows.length ? rows : [el("tr", {}, el("td", { colspan: 7 }, "No clipping detected on these laps."))]));
    svg.attr("aria-label", `Speed, speed difference and throttle by distance at ${meta.name}. ${sub.textContent}`);
  }

  function drawReadout() {
    if (!current()) return;
    const { brush: sel, zoom } = state.get();
    const r = summarize(cmp, sel);
    const stat = (label, value) => el("div", { class: "stat" }, el("span", {}, label), el("b", {}, value));
    const val = (v, f = kmh) => (v == null ? "–" : f(v));
    const bits = [stat(sel ? "Selected section" : "Section", sel ? `${metres(sel[0])} – ${metres(sel[1])}` : "Whole lap")];
    if (cmp.a) bits.push(stat("2025 average speed", val(r.a)));
    if (cmp.b) bits.push(stat("2026 average speed", val(r.b)));
    if (cmp.a && cmp.b) bits.push(stat("2026 minus 2025", val(r.diff, (v) => `${signed(v)} km/h`)));
    if (cmp.b) bits.push(stat("2026 inferred clipping", metres(r.clip)));
    if (r.missing) bits.push(stat("Without data", percent(r.missing / r.cells)));
    const zoomed = Boolean(zoom);
    const stats = el("div", { class: "stats" }, ...bits);
    const buttons = el("div", { class: "buttons" },
      el("button", { type: "button", disabled: !sel && !zoomed, onclick: () => state.set({ zoom: zoomed ? null : sel }, "zoom") },
        zoomed ? "Show whole lap" : "Zoom to selection"),
      el("button", { type: "button", disabled: !sel, onclick: () => state.set({ brush: null }, "clear") }, "Clear selection"));
    // Keep keyboard focus on the button that was just pressed.
    if (compact) return readout.replaceChildren(stats);
    const i = [...readout.querySelectorAll("button")].indexOf(document.activeElement);
    readout.replaceChildren(stats, buttons);
    if (i >= 0) [...readout.querySelectorAll("button")].find((b, j) => j >= i && !b.disabled)?.focus();
  }

  // --- wiring --------------------------------------------------------------------------
  state.on("brush", ORIGIN, ({ origin }) => {
    if (!current()) return;
    if (origin !== ORIGIN) syncBrush();
    drawReadout();
  });
  state.on("hover", ORIGIN, ({ origin }) => drawHover(origin));
  state.on("zoom", ORIGIN, () => { if (current()) { draw(); drawReadout(); } });

  const ro = new ResizeObserver(([entry]) => {
    const w = Math.round(entry.contentRect.width);
    if (w && w !== width) { width = w; draw(); }
  });
  ro.observe(chart);

  return {
    update(next) { cmp = next; anchor = null; drawText(); draw(); drawReadout(); },
    resize: draw,
    destroy() { ro.disconnect(); root.replaceChildren(); },
  };
}
