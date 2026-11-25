// Loads and caches site/data. Views receive a prepared `comparison`.
const cache = new Map();

async function load(path) {
  if (!cache.has(path)) {
    const p = fetch(path).then((r) => {
      if (!r.ok) throw new Error(`${path}: ${r.status}`);
      return r.json();
    });
    p.catch(() => cache.delete(path));
    cache.set(path, p);
  }
  return cache.get(path);
}

export const loadIndex = () => load("data/index.json");
export const loadSeason = () => load("data/season.json");
export const loadCircuit = (id) => load(`data/circuits/${id}.json`);

export const hasData = (pair) => Boolean(pair && (pair.a || pair.b));

// 2025 lap (a), 2026 lap (b) and their difference on the shared grid.
export function compare(circuit, pairId) {
  const pair = circuit.pairs.find((p) => p.id === pairId && hasData(p)) ?? circuit.pairs[0];
  const a = circuit.laps[pair.a] ?? null;
  const b = circuit.laps[pair.b] ?? null;
  const s = Array.from({ length: circuit.n }, (_, i) => i * circuit.step);
  const diff = s.map((_, i) =>
    a && b && a.speed[i] != null && b.speed[i] != null ? b.speed[i] - a.speed[i] : null);
  return { circuit, pair, a, b, s, diff, step: circuit.step, length: s[s.length - 1] };
}

export function zoneAt(lap, s) {
  return lap?.zones.find((z) => s >= z.s0 && s <= z.s1) ?? null;
}

// Averages over [s0, s1]; speeds use only cells where both laps have data.
export function summarize(cmp, range) {
  const [s0, s1] = range ?? [0, cmp.length];
  const out = { a: null, b: null, diff: null, clip: 0, missing: 0, cells: 0 };
  let na = 0, nb = 0, n = 0, sa = 0, sb = 0, sd = 0;
  cmp.s.forEach((s, i) => {
    if (s < s0 || s > s1) return;
    out.cells++;
    const va = cmp.a?.speed[i], vb = cmp.b?.speed[i];
    const both = va != null && vb != null;
    if (!both && cmp.a && cmp.b) out.missing++;
    if (both || !cmp.b) { if (va != null) { sa += va; na++; } }
    if (both || !cmp.a) { if (vb != null) { sb += vb; nb++; } }
    if (both) { sd += vb - va; n++; }
  });
  if (na) out.a = sa / na;
  if (nb) out.b = sb / nb;
  if (n) out.diff = sd / n;
  for (const z of cmp.b?.zones ?? []) out.clip += Math.max(0, Math.min(z.s1, s1) - Math.max(z.s0, s0));
  return out;
}
