import * as state from "./state.js";
import { loadIndex, loadSeason, loadCircuit, compare, hasData } from "./data.js";
import { createTrace } from "./views/trace.js";
import { createMap } from "./views/map.js";
import { createSeason } from "./views/season.js";
import { createHero, createMechanism } from "./views/hero.js";
import { createStory } from "./story.js";

const $ = (id) => document.getElementById(id);
const DEFAULT = "spa/driver-ant";        // the story's lead example
const views = [];
// Contrasting circuits for a first look. The last field is an optional section.
const STARTS = [
  ["Miami: the most clipping", { circuit: "miami", pair: "fastest" }],
  ["Singapore: none", { circuit: "singapore", pair: "fastest" }],
  ["Baku: a very long straight", { circuit: "baku", pair: "fastest" }],
  ["Spa: Kemmel, same driver", { circuit: "spa", pair: "driver-ant", brush: [1630, 2280] }],
];
let index, ticket = 0;

function option(value, text, disabled = false) {
  const o = new Option(text, value);
  o.disabled = disabled;
  return o;
}

function fillPairs(circuit, selected) {
  $("pair").replaceChildren(...circuit.pairs.map((p) => {
    const gap = !p.a && !p.b ? " (no data)" : "";
    return option(p.id, p.label + gap, !hasData(p));
  }));
  $("pair").value = selected;
}

// Load, then hand every view the same comparison. A slow response for a circuit
// the reader has already left is dropped.
async function refresh() {
  const mine = ++ticket;
  const { circuit: id, pair } = state.get();
  $("compare").style.opacity = 0.6;
  try {
    const circuit = await loadCircuit(id);
    if (mine !== ticket) return;
    const cmp = compare(circuit, pair);
    if (cmp.pair.id !== pair) return state.set({ pair: cmp.pair.id });
    $("circuit").value = id;
    fillPairs(circuit, cmp.pair.id);
    $("status").textContent = "";
    const meta = index.circuits.find((c) => c.id === id);
    for (const v of views) v.update({ ...cmp, meta });
  } catch (err) {
    if (mine === ticket) $("status").textContent = `Could not load this circuit (${err.message}).`;
  } finally {
    if (mine === ticket) $("compare").style.opacity = 1;
  }
}

async function start() {
  index = await loadIndex();
  for (const n of document.querySelectorAll("[data-th]")) n.textContent = index.thresholds[n.dataset.th];
  $("circuit").replaceChildren(...index.circuits.map((c) => option(c.id, c.name)));
  views.push(createMap($("map"), state), createTrace($("trace"), $("compare-head"), state));

  document.querySelector(".starts").replaceChildren(...STARTS.map(([text, to]) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = text;
    b.addEventListener("click", () => state.set({ brush: null, zoom: null, ...to }, "controls"));
    return b;
  }));

  const [season, spa] = await Promise.all([loadSeason(), loadCircuit("spa")]);
  const lead = { ...compare(spa, "driver-ant"), meta: index.circuits.find((c) => c.id === "spa") };
  createHero($("hero"), lead);
  createMechanism($("mechanism"));
  createStory($("story"), lead);
  createSeason($("season"), state).update({ index, season });

  state.on("selection", "main", refresh);
  $("circuit").addEventListener("change", (e) => state.set({ circuit: e.target.value }, "controls"));
  $("pair").addEventListener("change", (e) => state.set({ pair: e.target.value }, "controls"));
  window.addEventListener("hashchange", applyHash);
  applyHash();
  // A shared link to a circuit should open on it, once the charts above have their height.
  // The default state is also written to the URL; reloading that stays at the top.
  const hash = location.hash.slice(1);
  const at = hash.includes("/") && hash !== DEFAULT ? document.querySelector(".controls") : document.getElementById(hash || " ");
  at?.scrollIntoView();
}

function applyHash(event) {
  // "#method" and the like are places on the page, not states.
  if (event && document.getElementById(location.hash.slice(1))) return;
  const h = state.readHash();
  const known = index.circuits.some((c) => c.id === h.circuit);
  if (!known) {
    const [circuit, pair] = DEFAULT.split("/");
    return state.set({ circuit, pair });
  }
  state.set({ circuit: h.circuit, pair: h.pair || "fastest", brush: h.brush });
}

start().catch((err) => { $("status").textContent = `Could not start: ${err.message}`; });
