# Explorer code patterns

Lifted from `docs/system-design/explorer.html`. Copy and adapt; keep the behaviour.

## Theme tokens

```css
:root {
  --ground: #e8e6e1; --sheet: #fafaf7; --ink: #1c1b18; --ink-2: #4c4a44; --ink-3: #74716a;
  --hair: rgba(28,27,24,.09); --hair-2: rgba(28,27,24,.17);
  --accent: #2c59cc; --accent-soft: rgba(44,89,204,.15);
  --signal: #cf4527; --signal-soft: rgba(207,69,39,.17);
  --lift1: 0 1px 2px rgba(30,28,24,.06), 0 0 0 1px rgba(28,27,24,.05);
  --lift3: 0 12px 32px rgba(30,28,24,.11), 0 2px 6px rgba(30,28,24,.06), 0 0 0 1px rgba(28,27,24,.08);
  /* Motion: ease-out for arriving, ease-in for leaving, ease-in-out for toggles. No overshoot. */
  --ease-out: cubic-bezier(.16,1,.3,1); --ease-in: cubic-bezier(.7,0,.84,0); --ease-in-out: cubic-bezier(.65,0,.35,1);
  --dur-micro: 120ms; --dur-short: 220ms; --dur-long: 420ms;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { /* dark values */ color-scheme: dark; } }
:root[data-theme="dark"] { /* same dark values */ color-scheme: dark; }
```

## One section per key press

```js
(function sectionKeys() {
  const SECS = () => [...document.querySelectorAll(".mast, section.block")];
  const ease = p => p < .5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
  let busy = false;
  function glide(y) {
    y = Math.max(0, Math.min(y, document.documentElement.scrollHeight - innerHeight));
    if (reduced) { scrollTo({ top: y, behavior: "instant" }); return; }
    const y0 = scrollY, d = y - y0, dur = Math.min(900, 420 + Math.abs(d) * .25), t0 = performance.now();
    busy = true; document.documentElement.style.scrollBehavior = "auto";
    (function step(now) {
      const p = Math.min(1, (now - t0) / dur); scrollTo(0, y0 + d * ease(p));
      if (p < 1) requestAnimationFrame(step); else { busy = false; document.documentElement.style.scrollBehavior = ""; }
    })(t0);
  }
  const topOf = el => el.getBoundingClientRect().top + scrollY;
  addEventListener("keydown", e => {
    if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
    const down = ["ArrowDown", "PageDown"].includes(e.key) || (e.key === " " && !e.shiftKey);
    const up = ["ArrowUp", "PageUp"].includes(e.key) || (e.key === " " && e.shiftKey);
    if (!down && !up) return;
    if (e.target.closest?.("input, textarea, select, [contenteditable]")) return;
    if (e.key === " " && e.target.closest?.("button, a, [role=tab]")) return;
    e.preventDefault(); if (busy) return;
    const secs = SECS(), y = scrollY + 2;
    let i = 0; secs.forEach((s, k) => { if (topOf(s) <= y) i = k; });
    const cur = secs[i], bottom = topOf(cur) + cur.offsetHeight;
    if (down) {
      if (bottom - (scrollY + innerHeight) > 40) return glide(Math.min(scrollY + innerHeight * .85, bottom - innerHeight));
      if (secs[i + 1]) glide(topOf(secs[i + 1]));
    } else {
      if (scrollY - topOf(cur) > 40) return glide(Math.max(topOf(cur), scrollY - innerHeight * .85));
      if (secs[i - 1]) { const p = secs[i - 1]; glide(p.offsetHeight > innerHeight ? topOf(p) + p.offsetHeight - innerHeight : topOf(p)); }
    }
  });
})();
```

On screens of laptop size and up, give each `section.block` `min-height: 100svh` and center its content so a press lands on one whole "slide".

## ← / → routed to whatever is on screen

```js
const walks = []; window.hfWalks = walks;   // each entry: { sec, next, prev }
addEventListener("keydown", e => {
  if (!["ArrowLeft", "ArrowRight"].includes(e.key) || e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.target.closest?.("input, textarea, [role=tablist]")) return;
  const mid = innerHeight / 2;   // the walk whose section crosses the middle of the screen
  const w = walks.find(w => { const r = w.sec.getBoundingClientRect(); return r.top < mid && r.bottom > mid; });
  if (!w) return;
  e.preventDefault(); e.key === "ArrowRight" ? w.next() : w.prev();
});
```

## Walk engine

```js
function set(i) {
  at = Math.max(0, Math.min(steps.length - 1, i));
  stage.className = "stage " + ["at-" + at].concat(steps.map((_, k) => k <= at ? "ge-" + k : "")).join(" ").trim();
  stage.querySelectorAll("[data-act]").forEach(el => el.classList.toggle("act", el.dataset.act.split(" ").includes(String(at))));
  // update step list (cur / past), move the marker, render cue chips + drill button for steps[at]
}
```

Each step: `{ t: "Title that says the point", cue: ["short", "cue", "chips"], desc: "One faded sentence.", d: "nodeId" }`.

## 100% cost bar

```js
/* Illustrative shares; must add up to 100. One walk step per item, biggest first. */
const BILL = [["Photo storage", 30], ["Photo delivery", 25], ["Search compute", 15], /* ... */];
bar.innerHTML = BILL.map((b, i) => `<i data-act="${i + 1}" style="flex:${b[1]} 0 0">${b[1] >= 5 ? b[1] + "%" : ""}</i>`).join("");
// step 0 shows the whole bill (100%); step N highlights BILL[N-1] and tweens the big number to its share
```

## Learn-it data

```js
const LEARN = { pubsub: { what: "...", how: "...", why: "...", nums: "1M ÷ 86,400 ≈ 12/s ...", risk: "..." } };
const LEARN_LBL = [["what", "What it is"], ["how", "How it works"], ["why", "Why this choice"], ["nums", "The numbers"], ["risk", "What can go wrong"]];
```

Generate `speaker-notes-components.md` from the same object so the page and the notes never drift.
