// The difference scale reuses the season colors, so each hue keeps one meaning:
// blue = 2025 faster, orange = 2026 faster, grey = equal.
const d3 = window.d3;
export const DIFF_LIMIT = 40;       // km/h; larger differences share the end color
const MID = "#d4d3cd";

export const diffColor = d3.scaleDiverging([-DIFF_LIMIT, 0, DIFF_LIMIT],
  (t) => (t < 0.5 ? d3.interpolateLab("#2a78d6", MID)(t * 2) : d3.interpolateLab(MID, "#eb6834")(t * 2 - 1))).clamp(true);

// Centered moving average that ignores missing values but never fills them in.
export function smooth(values, half = 2) {
  return values.map((v, i) => (v == null ? null
    : d3.mean(values.slice(Math.max(0, i - half), i + half + 1).filter((d) => d != null))));
}

// Season view. Magnitude is one hue (2026's); the relative scale uses two other hues,
// because blue and orange already mean the seasons.
export const SHARE_LIMIT = 0.22, REL_LIMIT = 0.1;
export const NONE = "#efeeea";
const ramp = d3.interpolateRgbBasis(["#fbdccd", "#f3a67f", "#eb6834", "#b8481a", "#7d2c0b"]);
export const shareColor = (v) => (v <= 0 ? NONE : ramp(Math.min(1, v / SHARE_LIMIT)));
export const relColor = d3.scaleDiverging([-REL_LIMIT, 0, REL_LIMIT],
  (t) => (t < 0.5 ? d3.interpolateLab("#0f8a5f", "#e6e5e0")(t * 2) : d3.interpolateLab("#e6e5e0", "#6250d6")(t * 2 - 1))).clamp(true);
