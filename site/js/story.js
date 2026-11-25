// The Spa story: text steps on the left drive one sticky map and trace.
// It has its own store, so the explorer keeps whatever the reader chose there.
import { createState } from "./state.js";
import { createTrace } from "./views/trace.js";
import { createMap } from "./views/map.js";

const d3 = window.d3;

export function createStory(section, cmp) {
  const state = createState();
  const steps = [...section.querySelectorAll(".step")];
  const trace = createTrace(section.querySelector("#story-trace"), null, state, { compact: true, uid: "story" });
  const map = createMap(section.querySelector("#story-map"), state, { compact: true, maxHeight: innerHeight < 720 ? 160 : 230 });
  section.querySelector("#story-read").append(section.querySelector("#story-trace .readout"));
  state.set({ circuit: cmp.circuit.id, pair: cmp.pair.id });
  for (const v of [map, trace]) v.update(cmp);

  const calm = matchMedia("(prefers-reduced-motion: reduce)");
  const range = (text) => (text ? text.split("-").map(Number) : null);
  const full = [0, cmp.length];
  let active = null, timer = null;

  // Moves the trace's window smoothly, so the reader sees where on the lap they went.
  function zoomTo(target) {
    timer?.stop();
    const from = state.get().zoom ?? full;
    const done = () => state.set({ zoom: target[0] <= 0 && target[1] >= cmp.length ? null : target }, "story");
    if (calm.matches || document.hidden) return done();
    const at = d3.interpolateArray(from, target);
    timer = d3.timer((ms) => {
      const t = Math.min(1, ms / 700);
      if (t === 1) { timer.stop(); done(); } else state.set({ zoom: [...at(d3.easeCubicInOut(t))] }, "story");
    });
  }

  function activate(step) {
    if (step === active) return;
    active = step;
    for (const n of steps) n.classList.toggle("active", n === step);
    zoomTo(range(step.dataset.zoom).map((v) => Math.min(v, cmp.length)));
    state.set({ brush: range(step.dataset.brush), hover: null }, "story");
  }

  // A step is current while it crosses a thin band across the window.
  const observer = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) activate(e.target);
  }, { rootMargin: matchMedia("(max-width: 900px)").matches ? "-75% 0px -20% 0px" : "-50% 0px -45% 0px" });
  for (const n of steps) observer.observe(n);
  activate(steps[0]);
}
