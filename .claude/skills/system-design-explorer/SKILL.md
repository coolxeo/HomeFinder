---
name: system-design-explorer
description: Build a scrollable, drill-down system design explorer page (one HTML file) that a presenter walks through with the keyboard and a reviewer can explore alone. Use for architecture reviews, design interviews and committee walkthroughs.
---

# System design explorer

One self-contained HTML page that explains a system the way an architect would at a whiteboard: the decisions first, then the moving picture, then a walk through each hard part, with every box clickable for the long explanation. It works as a talk (keyboard, one section per key press) and as something a reviewer reads alone afterwards.

Reference build: `docs/system-design/explorer.html` in the HomeFinder repo (artifact "HomeFinder System Explorer"). Read it before starting a new one; most patterns below are lifted from it.

If `.claude/skills/hallmark` and `.claude/skills/frontend-design` exist, load them for the visual pass. This skill adds the structure, interaction and copy rules that are specific to explaining a system.

## 1. Before you build

1. Get the brief and the time budget. Note which sections the presenter must cover and how many minutes each gets. If the brief says "pick one option per section", ask the person to pick, recommend one, and build on your recommendation while you wait.
2. Lock the decisions with the person before drawing anything. Ask a few questions per round (eventing, data, cache, ML, search, regions), give the facts they need to answer, and record each answer as **one line plus why** in a study-notes markdown file. Those notes are speaker notes, never slide text.
3. Find the one rule the design hangs on and put it at the top (for HomeFinder: "managed where the protocol is open, proprietary only behind an adapter"). Every decision card should be explainable through it.
4. Write the capacity math once (users → daily → per second → peak) and reuse the exact same numbers everywhere. Mark every figure you invented as an assumption.

## 2. Page structure (top to bottom)

Each block is a full-screen `section.block`. Keep this order unless the brief forces another:

1. **Talk** (optional): the committee deck embedded at the top (see "Embedding a deck").
2. **Masthead + agenda**: one-sentence summary, then the talk's parts with minutes for each.
3. **Demo**: a playable animation of the core flow in about 5 chapters (for HomeFinder: ingest, resolve and store, geo cells, map search, alert). Listing cards with photos flowing through the system.
4. **Decisions**: cards grouped into lanes (Ingest, Store, Serve, Run). See "Decision cards".
5. **Architecture diagram**: animated, with named flows (listing update, search, alert). Click a node to drill in.
6. **Layers**: an isometric stack of at most 5 layers that follows one item from arrival to storage to read models. Not concepts, not "who does what".
7. **Numbers**: the capacity math as clickable figures.
8. **Walks**: one stepped walkthrough per hard part (pipeline, latency budget, geo indexing, alerts, cost).
9. **Terms**: a glossary of every acronym on the page.

Every component, number and decision opens the same drill-down sheet (section 5).

## 3. Copy rules (the person asked for these explicitly)

- **Titles say what the section shows and the decision behind it.** "Answering a map search in under 200 milliseconds", not "Search". No single-word titles.
- **Few acronyms.** Spell each one out the first time it appears, add a hover `title`, and list it in Terms. Drop an acronym entirely when the plain words are short enough.
- **No AI slop.** No "seamless", "robust", "leverage", "unlock", no tracked-out ALL-CAPS eyebrows on every heading, no "A · B · C" meta strings as decoration, no arrows appended to links. Read every line aloud; if a person wouldn't say it to a committee, rewrite it.
- **Decisions are one line plus why.** "Pub/Sub over Kafka: we have 12 events a second." Add the "switch if" trigger: the condition that would make you change the decision.
- **Cues on screen, explanation in the presenter's mouth.** On-screen text is short cue chips. A faded one- or two-sentence description sits under the selected step only.
- **Helper text is hidden by default** behind a notes toggle next to the theme switch (section 6). Hide subtitles, lead lines, minute labels, legend explanations, status labels, step descriptions. Keep titles, picks, numbers, colors and cue chips.
- **Remove labels that carry no information.** If every card is "1 of 3", drop the label.
- **Name nodes by what they are.** "Ingest workers (Cloud Run)", not "Ingest". Label edges with verbs ("schedule", "pull job", "purge").
- **Label fakes.** Made-up records and AI-generated photos say so on the page. Real MLS-style data is licensed; never scrape it for a demo.

## 4. Visual and motion rules

- **Light and dark for everything.** Tokens on `:root`, dark values under `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {...} }` and again under `:root[data-theme="dark"]`. A theme toggle at the end of the nav cycles system, light, dark and remembers the choice (localStorage in try/catch).
- **Warm grey ground, white sheets, soft lifts.** Four lift levels as box-shadow tokens. One accent (blue) for "chosen / in flow", one signal (orange-red) for "edge case / cost / warning".
- **One channel per meaning.** If color means category, it cannot also mean risk. HomeFinder's reversibility ring was colored by category and confused the presenter; it is now neutral grey with the letter (L/M/H) and arc length carrying reversibility.
- **Motion tokens, no overshoot:** `--ease-out: cubic-bezier(.16,1,.3,1)` for arrivals, `--ease-in: cubic-bezier(.7,0,.84,0)` for exits, `--ease-in-out: cubic-bezier(.65,0,.35,1)` for toggles; `--dur-micro: 120ms; --dur-short: 220ms; --dur-long: 420ms`.
- Sliding highlight under tabs and nav, a marker that follows the current step, cards staggered by about 70 ms, numbers that count to their new value. Everything off under `prefers-reduced-motion`.
- **Diagram edges** are dotted paths with moving dash offset and packets traveling along the active flow. The diagram must reflect real control flow: if a queue triggers a worker, draw source → queue → worker, not two arrows into the worker.
- **Icons**: Lucide, inlined as SVG paths (credit "Lucide (ISC)" in the README). One icon per decision card in a small tile.
- **Maps in demos**: main roads and highways only, a lake and a park for orientation, no small streets, no road crossing a park, no label colliding with an overlay.
- Check at 390 px wide: no sideways scroll, diagram nodes in the right place, tables fit.

## 5. Components

### Decision cards
- Lanes look like Trello lists: a plain heading with a count ("Ingest 3") and the cards grouped on a shaded lane. No heading cards.
- A card shows: icon tile, decision title, the pick, a short reason, a category color dot, a key number, and a reversibility ring (L/M/H).
- No hover effects inside cards. Click opens the sheet with all options (chosen and rejected, each with a one-line why), the switch trigger and a link to the node in the diagram.
- A ledger bar across the top shows every decision as one segment, **grouped by color** (all of the first category, then the next), with filter chips in the same order.
- Data model per decision: `[id, title, pick, pickWhy, category, number, reversibility(1-3), switchIf, nodeId, [[option, oneLineWhy] x3]]`.

### Drill-down sheet ("Learn it")
Every node, number and decision opens one sheet with a "Say it" line, likely questions, and a **Learn it** block with five fixed headings: **What it is**, **How it works**, **Why this choice**, **The numbers** (worked, like 1M ÷ 86,400 ≈ 12/s), **What can go wrong**. Store it as one `LEARN = { id: {what, how, why, nums, risk} }` object, and write the same text to `speaker-notes-components.md` in talk order so it can be turned into a podcast. The sheet is deep-linkable (`#x-<id>`).

### Walks
A walk is a stage plus an ordered list of steps. Each step has a title, 2-4 cue chips, a faded description and a drill link. The stage gets classes `at-N` and `ge-0..N`, and elements tagged `data-act="2 3"` light up on those steps, so CSS does the animation. "Play the steps" auto-advances; clicking a step or the stage moves one step.

**Charts in walks stay dumb.** A cost walk is one fixed bar that adds up to 100%; each step highlights one line item, biggest first, and shows its share. No regrouping, no bars changing size.

### Demo playback
- Default speed **0.5x**, with a 0.5x / 1x toggle, also on the architecture animation.
- **Play step** plays one chapter and stops on its last frame; pressing it again plays the next. **Play all** runs to the end. Clicking a chapter plays just that chapter. ← / → play the previous or next chapter while the demo is on screen.
- Merges and dedupes must read at a glance: the second copy arrives with a "Duplicate" badge and a "same address" link, then folds behind the first, which turns to "1 id · 2 sources". Never leave two cards stacked on top of each other.

### Keyboard model
- ↓ / ↑, Page Down / Up and Space glide exactly one section with an eased scroll (cubic in-out, 420-900 ms). A section taller than the screen pages through itself (85% of the viewport per press) before moving on.
- ← / → go to whichever stepped thing is on screen: walks, the demo, the embedded deck. Keep a registry `window.hfWalks = [{ sec, next, prev }]`; the arrow handler picks the entry whose section crosses the middle of the screen.
- N toggles presenter notes in the deck, F full screen. Ignore keys with modifiers and inside inputs; never steal Space from a focused button.

### Embedding a deck
Put the keyboard deck in a shadow root inside the Talk section so its CSS cannot leak, scale its 1920×1080 stage to the container (`aspect-ratio: 16/9`), register it in `hfWalks`, and expose `window.talkDeck = { next, prev, restart, notes, full }` for buttons under the stage. Regenerate the embed from the deck source with a build script rather than hand-editing the copy.

## 6. Notes toggle (pattern)

```css
:root:not(.notes) :is(.sec-lead, .hint, .sdesc, .ag-time, .legend .hintx) { display: none !important; }
```
```js
function applyNotes(on) { document.documentElement.classList.toggle("notes", on); /* swap captions / captions-off icon, aria-pressed */ }
try { applyNotes(localStorage.getItem("notes") === "on"); } catch (e) { applyNotes(false); }
```

## 7. Review loop (do this every round)

1. Screenshot light, dark and a 390 px phone with Playwright; check the console has no errors and `document.documentElement.scrollWidth <= innerWidth`.
2. Press ↓ through the whole page and → through every walk; confirm nothing is skipped.
3. Check every decided component appears in the overview diagram (HomeFinder shipped a system overview without the cache once).
4. Grep for every number across the explorer, deck, study notes and speaker notes; they must agree (burst rate, latency budget, retention days drifted apart in HomeFinder).
5. Read every title and caption aloud against the copy rules.
6. Republish to the same artifact URL and push to the repo.

## 8. Pitfalls seen

- Too much interactivity: hovering bars inside cards that rewrote subtitles. The person wanted the card static with a color dot.
- Two threads editing the same page: always start from the latest published version or the newest PR branch, never an older local copy.
- Secrets: an API key pasted in chat must never land in a file, commit or script. Read keys from an environment variable and tell the person to rotate a key that was pasted.
- Diagram edges that described data flow but not control flow, and node labels that named a stage instead of a system.
- Animations that were too fast to narrate; hence 0.5x default and play-step.
