import { el } from "./format.js";

// A tooltip inside `host`; positions are in host pixels and stay within it.
// Pass y = "bottom" to dock it to the host's lower edge.
export function createTooltip(host) {
  const node = el("div", { class: "tooltip", hidden: true, "aria-hidden": "true" });
  host.append(node);
  return {
    show(x, y, ...content) {
      node.replaceChildren(...content.filter(Boolean));
      node.hidden = false;
      const w = node.offsetWidth, W = host.clientWidth;
      const left = x + 16 + w > W ? x - 16 - w : x + 16;
      if (y === "bottom") y = Math.max(0, host.clientHeight - node.offsetHeight);
      node.style.transform = `translate(${Math.max(0, left)}px, ${y}px)`;
    },
    hide() { node.hidden = true; },
  };
}
