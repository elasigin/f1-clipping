// View 3: how much each team clips at each circuit across the 2026 season.
import { el, metres, kmh, percent } from "../format.js";
import { createTooltip } from "../tooltip.js";
import { shareColor, relColor, NONE, SHARE_LIMIT, REL_LIMIT } from "../scales.js";

const d3 = window.d3;
const ORIGIN = "season";
const M = { top: 22, right: 168, bottom: 116, left: 196 };
const STRIP_H = 108, GAP = 30, ROW = 25, GROUP_GAP = 9;
const points = (v) => `${d3.format("+.1f")(v * 100).replace("-", "−")} pts`;

export function createSeason(root, state) {
  const modes = [["abs", "Share of full throttle"], ["rel", "Compared with circuit median"]].map(([m, text]) =>
    el("button", { type: "button", "data-mode": m, onclick: () => state.set({ mode: m }, ORIGIN) }, text));
  const toggle = el("div", { class: "toggle", role: "group", "aria-label": "Cell color shows" }, ...modes);
  const legend = el("ul", { class: "legend" });
  const chart = el("div", { class: "chart season-chart" });
  const hint = el("p", { class: "hint" }, "Select a cell to load that circuit and team in the explorer below. Keyboard: arrow keys move between cells, Enter selects.");
  const notes = el("p", { class: "hint" });
  const tableBody = el("div", { class: "table-wrap" });
  root.append(toggle, legend, el("div", { class: "scroll-x" }, chart), hint, notes,
    el("details", {}, el("summary", {}, "2026 clipping share as a table"), tableBody));

  const svg = d3.select(chart).append("svg").attr("role", "group").attr("aria-label", "Season heatmap of inferred clipping");
  const pat = svg.append("defs").append("pattern").attr("id", "hatch-none").attr("width", 6).attr("height", 6)
    .attr("patternUnits", "userSpaceOnUse").attr("patternTransform", "rotate(45)");
  pat.append("rect").attr("width", 6).attr("height", 6).attr("fill", "#fcfcfb");
  pat.append("line").attr("y2", 6).attr("stroke", "#b5b4ad").attr("stroke-width", 1.5);
  const g = svg.append("g").attr("transform", `translate(${M.left},${M.top})`);
  const layer = Object.fromEntries(["grid", "strip", "cells", "labels", "side"].map((k) => [k, g.append("g").attr("class", k)]));
  const tip = createTooltip(chart);

  let data = null, width = 0, focus = [0, 0];

  // --- preparation ---------------------------------------------------------------------
  function prepare({ index, season }) {
    const value = new Map(season.rows.map((r) => [`${r.season}|${r.circuit}|${r.team}`, r]));
    const get = (yr, c, t) => value.get(`${yr}|${c}|${t}`) ?? null;
    const summary = new Map(season.teams.map((t) => [t.team, t]));
    const circuits = index.circuits.map((c) => {
      const of = (yr, k) => season.rows.filter((r) => r.season === yr && r.circuit === c.id).map((r) => r[k]);
      return { ...c, date: new Date(`${c.date2026}T12:00:00`), m25: d3.median(of(2025, "share")) ?? null,
        m26: d3.median(of(2026, "share")) ?? null, lo: d3.median(of(2026, "lo")), hi: d3.median(of(2026, "hi")) };
    });
    // Rows grouped by 2026 power unit; suppliers and teams in a fixed order.
    const groups = d3.groups(index.teams, (t) => t.pu2026);
    let y = 0;
    const teams = [];
    for (const [pu, members] of groups) {
      members.forEach((t, i) => {
        teams.push({ ...t, label: t.name.split(" / ")[0], pu, first: i === 0, y, ...summary.get(t.id) });
        y += ROW;
      });
      y += GROUP_GAP;
    }
    const cells = teams.flatMap((t, row) => circuits.map((c, col) => {
      const r = get(2026, c.id, t.id), old = get(2025, c.id, t.id);
      return { row, col, team: t, circuit: c, r, old, rel: r ? r.share - c.m26 : null };
    }));
    return { circuits, teams, cells, heatH: y - GROUP_GAP, rules: season.ruleChanges };
  }

  const fill = (d) => (!d.r ? "url(#hatch-none)" : state.get().mode === "rel" ? relColor(d.rel) : shareColor(d.r.share));
  const why = (c) => c.reason ?? "No usable telemetry.";

  // --- drawing ----------------------------------------------------------------------------
  function draw() {
    width ||= chart.clientWidth;
    if (!data || !width) return;
    const W = width - M.left - M.right;
    const x = d3.scaleBand(d3.range(data.circuits.length), [0, W]).paddingInner(0.06);
    const heatY = STRIP_H + GAP, H = heatY + data.heatH;
    svg.attr("viewBox", `0 0 ${width} ${M.top + H + M.bottom}`);
    drawStrip(x, W);
    drawCells(x, heatY);
    drawLabels(x, heatY, H);
    drawSide(W, heatY);
    drawCurrent();
  }

  function drawStrip(x, W) {
    const y = d3.scaleLinear([0, 0.25], [STRIP_H, 0]);
    layer.grid.selectAll("*").remove();
    layer.strip.selectAll("*").remove();
    for (const t of [0, 0.1, 0.2]) {
      layer.grid.append("line").attr("x2", W).attr("y1", y(t)).attr("y2", y(t)).attr("stroke", t ? "var(--grid)" : "var(--rule)");
      layer.grid.append("text").attr("x", -8).attr("y", y(t)).attr("dy", "0.32em").attr("text-anchor", "end").text(d3.format(".0%")(t));
    }
    layer.grid.append("text").attr("class", "strong").attr("x", -M.left).attr("y", 4).text("Circuit median,");
    layer.grid.append("text").attr("class", "strong").attr("x", -M.left).attr("y", 20).text("share of full throttle");
    data.circuits.forEach((c, i) => {
      const cx = x(i) + x.bandwidth() / 2;
      // Side by side, so a 2025 dot at zero is never hidden behind 2026's.
      const c25 = cx - 6, c26 = cx + 6;
      if (c.m26 != null) {
        layer.strip.append("line").attr("class", "range y2026").attr("x1", c26).attr("x2", c26).attr("y1", y(c.lo)).attr("y2", y(c.hi));
      }
      if (c.m25 != null) layer.strip.append("circle").attr("class", "dot y2025").attr("r", 5).attr("cx", c25).attr("cy", y(c.m25));
      if (c.m26 != null) layer.strip.append("circle").attr("class", "dot y2026").attr("r", 5).attr("cx", c26).attr("cy", y(c.m26));
      layer.strip.append("rect").attr("x", x(i)).attr("y", -6).attr("width", x.bandwidth()).attr("height", STRIP_H + 14)
        .attr("fill", "transparent").on("pointermove", (e) => tipCircuit(e, c)).on("pointerleave", () => tip.hide());
    });
  }

  function drawCells(x, heatY) {
    layer.cells.attr("transform", `translate(0,${heatY})`);
    layer.cells.selectAll("rect").data(data.cells).join("rect").attr("class", "cell")
      .attr("x", (d) => x(d.col)).attr("y", (d) => d.team.y).attr("width", x.bandwidth()).attr("height", ROW - 2).attr("rx", 2)
      .attr("fill", fill).attr("role", "button").attr("aria-label", describe)
      .attr("tabindex", (d) => (d.row === focus[0] && d.col === focus[1] ? 0 : -1))
      .on("pointermove", (e, d) => tipCell(d3.pointer(e, chart), d)).on("pointerleave", () => tip.hide())
      .on("focus", (e, d) => {
        if (!e.target.matches(":focus-visible")) return;
        const b = e.target.getBoundingClientRect(), h = chart.getBoundingClientRect();
        tipCell([b.right - h.left, b.top - h.top], d);
      })
      .on("blur", () => tip.hide())
      .on("click", (e, d) => choose(d)).on("keydown", move);

    // Rule changes fall between two columns, whatever the rows show.
    layer.labels.selectAll("*").remove();
    for (const r of data.rules) {
      const i = data.circuits.findIndex((c) => c.id === r.before);
      const px = x(i) - (x.step() - x.bandwidth()) / 2;
      layer.labels.append("line").attr("class", "rule").attr("x1", px).attr("x2", px).attr("y1", -8).attr("y2", heatY + data.heatH + 4);
      layer.labels.append("text").attr("class", "halo").attr("x", px + 5).attr("y", -10).text(r.label);
    }
  }

  function drawLabels(x, heatY, H) {
    const date = d3.timeFormat("%b %-d");
    for (const [i, c] of data.circuits.entries()) {
      const t = layer.labels.append("text").attr("class", "col").attr("data-id", c.id).attr("text-anchor", "end")
        .attr("transform", `translate(${x(i) + x.bandwidth() / 2 + 4},${H + 14}) rotate(-48)`);
      t.text(`${c.short}${c.status === "low" ? "*" : ""}`);
      t.append("tspan").attr("dx", 5).attr("fill", "#6b6a66").text(date(c.date));
    }
    for (const t of data.teams) {
      const yy = heatY + t.y + (ROW - 2) / 2;
      if (t.first) layer.labels.append("text").attr("class", "strong").attr("x", -M.left).attr("y", yy).attr("dy", "0.34em").text(t.pu);
      layer.labels.append("text").attr("class", "row").attr("data-id", t.id).attr("x", -10).attr("y", yy)
        .attr("dy", "0.34em").attr("text-anchor", "end").text(t.label);
    }
  }

  // Team averages: a dot, plus an interval in the relative view so that small gaps read as small.
  function drawSide(W, heatY) {
    const rel = state.get().mode === "rel";
    const s = layer.side.attr("transform", `translate(${W + 26},${heatY})`);
    s.selectAll("*").remove();
    const w = M.right - 46;
    const x = rel ? d3.scaleLinear([-0.04, 0.04], [0, w]).clamp(true) : d3.scaleLinear([0, 0.2], [0, w]);
    const ticks = rel ? [-0.04, 0, 0.04] : [0, 0.1, 0.2];
    for (const t of ticks) {
      s.append("line").attr("x1", x(t)).attr("x2", x(t)).attr("y1", -4).attr("y2", data.heatH).attr("stroke", t === 0 ? "var(--rule)" : "var(--grid)");
      s.append("text").attr("x", x(t)).attr("y", data.heatH + 16).attr("text-anchor", "middle")
        .text(rel ? (t ? d3.format("+.0f")(t * 100).replace("-", "−") : "0") : d3.format(".0%")(t));
    }
    s.append("text").attr("class", "strong").attr("x", -4).attr("y", -26).text("Team average");
    s.append("text").attr("x", -4).attr("y", -11).text(rel ? "vs median, points" : "across circuits");
    for (const t of data.teams) {
      const yy = t.y + (ROW - 2) / 2;
      if (rel) s.append("line").attr("class", "ci").attr("x1", x(t.relLo)).attr("x2", x(t.relHi)).attr("y1", yy).attr("y2", yy);
      s.append("circle").attr("class", "mean").attr("r", 5).attr("cx", x(rel ? t.rel : t.mean)).attr("cy", yy);
      s.append("rect").attr("x", -10).attr("y", t.y).attr("width", w + 30).attr("height", ROW).attr("fill", "transparent")
        .on("pointermove", (e) => tipTeam(e, t)).on("pointerleave", () => tip.hide());
    }
  }

  function drawCurrent() {
    const { circuit, pair } = state.get();
    layer.cells.selectAll("rect").classed("current", (d) => d.circuit.id === circuit && d.team.id === pair)
      .filter(".current").raise();
    layer.labels.selectAll("text.col").classed("strong", function () { return this.dataset.id === circuit; });
    layer.labels.selectAll("text.row").classed("strong", function () { return this.dataset.id === pair; });
  }

  // --- tooltips -------------------------------------------------------------------------------
  function tipCell([px, py], d) {
    const head = el("div", { class: "where" }, `${d.team.label}, ${d.circuit.name} 2026`);
    if (!d.r) return tip.show(px, py, head, el("div", {}, why(d.circuit)));
    const r = d.r, row = (v, label) => el("div", { class: "row" }, el("b", {}, v), el("span", {}, label));
    tip.show(px, py, head, row(percent(r.share), "of full-throttle distance"), row(points(d.rel), "vs circuit median"),
      row(metres(r.clipM), `in ${r.sec} s, ${r.driver}`),
      r.maxDrop ? row(kmh(r.maxDrop), "biggest single loss") : null,
      d.old ? row(percent(d.old.share), `2025 ${d.old.driver}`) : null,
      el("div", { class: "zone-note" }, `Stricter to looser rules: ${percent(r.lo)} to ${percent(r.hi)}` +
        (r.status === "masked" ? `. ${percent(1 - r.coverage)} of the lap has no telemetry.` : r.status === "replaced" ? ". Team's best lap had broken telemetry; next best used." : "")));
  }
  function tipCircuit(e, c) {
    const row = (yr, v) => el("div", { class: "row" }, el("span", { class: "key", style: `border-color:var(--y${yr})` }),
      el("b", {}, v == null ? "wet" : percent(v)), el("span", {}, `${yr} median of teams`));
    tip.show(...d3.pointer(e, chart), el("div", { class: "where" }, c.name), row(2026, c.m26), row(2025, c.m25),
      c.m26 == null ? null : el("div", { class: "zone-note" }, `Stricter to looser rules: ${percent(c.lo)} to ${percent(c.hi)}`),
      c.reason ? el("div", { class: "zone-note" }, c.reason) : null);
  }
  function tipTeam(e, t) {
    tip.show(...d3.pointer(e, chart), el("div", { class: "where" }, `${t.label}, ${t.n} circuits`),
      el("div", { class: "row" }, el("b", {}, percent(t.mean)), el("span", {}, "average share")),
      el("div", { class: "row" }, el("b", {}, points(t.rel)), el("span", {}, "vs circuit median")),
      el("div", { class: "zone-note" }, `95% interval ${points(t.relLo)} to ${points(t.relHi)}`));
  }
  const describe = (d) => `${d.team.label}, ${d.circuit.name}: ` + (d.r
    ? `${percent(d.r.share)} of full-throttle distance, ${points(d.rel)} against the circuit median` : why(d.circuit));

  // --- selecting ---------------------------------------------------------------------------------
  function choose(d) {
    tip.hide();
    focus = [d.row, d.col];
    state.set({ circuit: d.circuit.id, pair: d.team.id, brush: null, zoom: null }, ORIGIN);
    const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
    document.querySelector(".controls")?.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "start" });
  }

  function move(e, d) {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); return choose(d); }
    const step = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] }[e.key];
    if (!step) return;
    e.preventDefault();
    focus = [Math.max(0, Math.min(data.teams.length - 1, d.row + step[0])),
      Math.max(0, Math.min(data.circuits.length - 1, d.col + step[1]))];
    layer.cells.selectAll("rect").attr("tabindex", (c) => (c.row === focus[0] && c.col === focus[1] ? 0 : -1))
      .filter((c) => c.row === focus[0] && c.col === focus[1]).node().focus();
  }

  // --- text ------------------------------------------------------------------------------------------
  function drawText() {
    const rule = data.rules[0];
    notes.replaceChildren("One qualifying lap per team per circuit. Thin orange lines span stricter to looser detection rules, so trust the pattern across circuits more than any single value. ",
      "Energy limits also vary by circuit, and the rules changed from Miami (", el("a", { href: rule.source }, "FIA, April 2026"),
      "), so compare teams within a column, and be careful reading improvement along a row. * Lower-confidence alignment.");
    const head = el("tr", {}, el("th", { scope: "col" }, "Team"), ...data.circuits.map((c) => el("th", { scope: "col" }, c.short)));
    const body = data.teams.map((t) => el("tr", {}, el("th", { scope: "row", style: "text-align:left" }, t.label),
      ...data.cells.filter((d) => d.team.id === t.id).map((d) => el("td", {}, d.r ? percent(d.r.share) : "no data"))));
    tableBody.replaceChildren(el("table", {}, el("thead", {}, head), el("tbody", {}, ...body)));
  }

  function drawMode() {
    const rel = state.get().mode === "rel";
    for (const b of modes) b.setAttribute("aria-pressed", b.dataset.mode === state.get().mode);
    const grad = (f, a, b) => `background:linear-gradient(to right,${d3.range(0, 1.01, 0.1).map((t) => f(a + t * (b - a))).join(",")})`;
    const sw = (style) => el("span", { class: "swatch", style });
    const hatch = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    hatch.setAttribute("width", 18); hatch.setAttribute("height", 12);
    d3.select(hatch).append("rect").attr("width", 18).attr("height", 12).attr("fill", "url(#hatch-none)");
    const dot = (yr) => { const n = document.createElementNS("http://www.w3.org/2000/svg", "svg"); n.setAttribute("width", 12); n.setAttribute("height", 12); d3.select(n).append("circle").attr("class", `dot y${yr}`).attr("cx", 6).attr("cy", 6).attr("r", 5); return n; };
    legend.replaceChildren(...(rel
      ? [el("li", {}, "less than median", el("span", { class: "ramp", style: grad(relColor, -REL_LIMIT, REL_LIMIT) }), "more than median (±10 points)")]
      : [el("li", {}, sw(`background:${NONE};border:1px solid var(--rule)`), "none detected"),
        el("li", {}, "a little", el("span", { class: "ramp", style: grad(shareColor, 0.002, SHARE_LIMIT) }), `${d3.format(".0%")(SHARE_LIMIT)} of full throttle`)]),
    el("li", {}, hatch, "wet, no data"), el("li", {}, dot(2026), "2026 circuit median"), el("li", {}, dot(2025), "2025 circuit median"));
    if (data) { layer.cells.selectAll("rect").attr("fill", fill); draw(); }
  }

  // --- wiring --------------------------------------------------------------------------------------------
  state.on("mode", ORIGIN, drawMode);
  state.on("selection", ORIGIN, () => { if (data) drawCurrent(); });
  const ro = new ResizeObserver(([entry]) => {
    const w = Math.round(entry.contentRect.width);
    if (w && w !== width) { width = w; draw(); }
  });
  ro.observe(chart);

  return {
    update(next) { data = prepare(next); drawText(); drawMode(); },
    resize: draw,
    destroy() { ro.disconnect(); root.replaceChildren(); },
  };
}
