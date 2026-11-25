// One store for everything the views share. Distances are metres along the
// circuit's reference line, the only coordinate all views have in common.
//
//   circuit  circuit id          brush  [s0, s1] selected section, or null
//   pair     lap-pair id         hover  s under the pointer, or null
//   mode     "abs" or "rel" (season) zoom   [s0, s1] shown by the trace, or null
//
// Every event carries the `origin` that caused it, so a view can ignore its own.
// The page has two stores: the main one below, and the story's, so that scrolling
// the story never disturbs what the reader selected elsewhere.
const d3 = window.d3;

const same = (a, b) => a === b || (Array.isArray(a) && Array.isArray(b) && a[0] === b[0] && a[1] === b[1]);

export function createState({ onChange } = {}) {
  const dispatcher = d3.dispatch("selection", "brush", "hover", "zoom", "mode");
  const state = { circuit: null, pair: "fastest", brush: null, hover: null, zoom: null, mode: "abs" };

  const get = () => state;

  function on(type, name, fn) {
    dispatcher.on(`${type}.${name}`, fn);
  }

  function set(patch, origin = "app") {
    const next = { ...patch };
    // A new circuit has new distances, so a section from the old one means nothing.
    if ("circuit" in next && next.circuit !== state.circuit) {
      next.brush ??= null;
      next.zoom ??= null;
      next.hover = null;
    }
    const changed = Object.keys(next).filter((k) => !same(next[k], state[k]));
    if (!changed.length) return;
    for (const k of changed) state[k] = next[k];
    // Selection first: views must have new data before they draw a brush on it.
    if (changed.includes("circuit") || changed.includes("pair")) {
      dispatcher.call("selection", null, { origin });
    }
    for (const k of ["mode", "zoom", "brush", "hover"]) {
      if (changed.includes(k)) dispatcher.call(k, null, { origin });
    }
    if (changed.some((k) => k !== "hover")) onChange?.();
  }

  return { get, on, set };
}

const main = createState({ onChange: () => writeHash() });
export const { get, on, set } = main;

// --- URL hash: #spa/mercedes/1600-2300  (a bookmarkable demo state) ------------
let hashTimer;
function writeHash() {
  clearTimeout(hashTimer);
  hashTimer = setTimeout(() => {
    const state = get();
    const b = state.brush ? `/${Math.round(state.brush[0])}-${Math.round(state.brush[1])}` : "";
    history.replaceState(null, "", `#${state.circuit}/${state.pair}${b}`);
  }, 150);
}

export function readHash() {
  const [circuit, pair, range] = location.hash.slice(1).split("/");
  const m = /^(\d+)-(\d+)$/.exec(range ?? "");
  return { circuit, pair, brush: m && +m[1] < +m[2] ? [+m[1], +m[2]] : null };
}
