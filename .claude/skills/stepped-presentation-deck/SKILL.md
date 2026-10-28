---
name: stepped-presentation-deck
description: Build a timed talk deck for a committee, interview or review: a keyboard-stepped animated HTML deck with presenter notes and a timer, plus an optional PowerPoint rehearsal version with the talk track in the notes.
---

# Stepped presentation deck

A deck where every → press plays the next reveal and lets it settle, so the presenter controls the pace and the motion still feels like a film. It ships as one HTML file (a 1920×1080 stage scaled to any screen), and optionally as a .pptx for rehearsal in PowerPoint's Presenter View.

Reference builds in the HomeFinder repo, `docs/system-design/`:
- `committee-deck.html`: the version shown to the committee (18 chapters, timed to the brief, N for notes with a 30:00 timer).
- `explorer-deck.html`: the prep version, made from the rehearsal video's scenes.
- Project file `homefinder-pitch-rehearsal.pptx`: 12 slides, native charts, the two-host talk track in the speaker notes.

If the podcast-rehearsal-video skill was used first, reuse its scene code: the same `render(t)` drives both the video and this deck.

## 1. Plan the talk against the brief

1. Copy the brief's deliverables and minutes into a table. For HomeFinder: high-level architecture 8 min, deep dive 15 min, scaling or cost 7 min, then wrap-up, inside 30 minutes plus 30 of questions.
2. If the brief says "pick one option per section", the person picks; recommend one and say why.
3. **Gap check.** List every requirement, target and constraint in the brief and mark where the deck answers it. HomeFinder's first committee pass was missing: the performance targets slide, all data sources (not just the main feed), the recommendations engine the brief listed, index sharding, map pins under 300 ms, freshness and failure modes, cost levers, and risks and compliance (privacy law, fair housing, lending disclosure, seasonal traffic). Add a slide or a step for each gap, or say in the notes why it's out of scope.
4. Group chapters into sections with a minute budget: `SECTIONS = [{ name: "01 · High-level architecture", min: 8, ids: [...] }, ...]`. The header shows the current section and its budget.
5. Open with the shape of the problem in numbers, give the one rule the design hangs on, then the decisions with a "why not X" for each push back you expect, and close in 20 seconds with the rule and the switch triggers.

## 2. Audience and tone

- **Committee deck:** speaks to the room. No hosts, no captions, no "pitch rehearsal" wording, no rehearsal coaching. Notes are cues, not a script.
- **Prep deck:** may keep coaching wording, but still no voices, captions or speaker bubbles on screen. When the person says "exactly like the video", reuse the visuals and motion, not the podcast parts.
- Keep the same visual style across the prep deck, committee deck and explorer so the person rehearses on what they present.

## 3. Copy rules

- Slide titles state the point: "One queue per MLS, one golden record, one fan-out". Push-back slides are titled as the question: "Push back: why not Kafka?".
- **Little text on the slide.** A big number with a short note under it ("H3 cells + OpenSearch", "precomputed nightly"); the long explanation goes in the presenter notes.
- Spell out acronyms on first use; drop the ones the room doesn't need.
- Comparison slides: two or three cards, CHOSEN vs NOT NOW tags, three ticks or crosses each, one line per tick.
- Remove anything the presenter can't defend or that doesn't fit the story; the person cut two lines from the geo slide because they didn't belong.
- Mark assumed figures as assumptions in the notes, and be ready to say how each was derived.
- No AI slop: no filler adjectives, no decorative eyebrows, no sentence the presenter wouldn't say out loud.

## 4. HTML deck engine

Stage and fit:
```js
// #deck is 1920x1080, absolutely positioned; scale it into the window
function fit() { const s = Math.min(innerWidth / 1920, innerHeight / 1080);
  deck.style.transform = `translate(${(innerWidth - 1920 * s) / 2}px, ${(innerHeight - 1080 * s) / 2}px) scale(${s})`; }
```

Scenes are built once and drawn from a single clock `t` (seconds). Each builder creates its elements and returns `draw(lt, L)`, where `lt` is time since the scene started and `L[k]` is when beat k starts:
```js
const eo = p => 1 - Math.pow(1 - p, 3), cl = v => Math.max(0, Math.min(1, v));
const E = (t, a, d = .7) => eo(cl((t - a) / d));                     // 0→1 starting at a, over d seconds
const sh = (el, p, dy = 26) => { el.style.opacity = p; el.style.transform = `translateY(${(1 - p) * dy}px)`; };
B.kafka = el => { const a = mk(el, "...", "card vs"), b = mk(el, "...", "card vs");
  return (t, L) => { sh(a, E(t, L[1] + 1.2)); sh(b, E(t, L[1] + 3.7)); }; };
```

**Stops** are the moments where a new box has settled. → tweens the clock from the current stop to the next, so the reveal plays and stops:
```js
const STOPS = { kafka: L => [.5, L[1] + 1.2, L[1] + 3.7, L[2] + .4], /* one entry per scene */ };
function go(n) {
  n = Math.max(0, Math.min(stops.length - 1, n)); if (n === k && !anim) return;
  const from = anim ? anim.b : tNow, to = stops[n].t, fwd = to > from;
  const d = reduce ? 1 : fwd ? Math.min(1900, Math.max(750, 500 + (to - from) * 120)) : 450;  // back is a quick rewind
  if (anim) tNow = anim.b;
  k = n; anim = { a: tNow, b: to, s: performance.now(), d };
  history.replaceState(null, "", "#s" + (k + 1));                    // reload lands on the same step
}
// in requestAnimationFrame: tNow = anim.a + (anim.b - anim.a) * easeInOutCubic(p); render(tNow);
```

When one idea is a set (six requirement cards), show the whole set in **one** stop. Don't make the presenter press → six times.

Keys: → Space PageDown Enter = next; ← PageUp Backspace = back; ↓ = next chapter; ↑ = start of this chapter, then previous chapter; Home / End; **N** = presenter notes; **F** = full screen. Click the right two thirds to advance, the left third to go back. Ignore keys with modifiers. Show a hint row at the bottom: current chapter, keys, `k / total`.

Presenter notes (N): a panel with the section name, a timer started on the first key press showing `mm:ss / 30:00` that turns signal-red past the budget, and the chapter's notes as bold cues: `NOTES = { overview: "Three rows. <b>Top: requests</b> ... <b>Valkey first</b> ..." }`.

Background life: a dotted grid drifting slowly and two large blurred glows on slow sine paths, driven by wall-clock time so the stage never looks frozen between presses. Respect `prefers-reduced-motion` (instant jumps, no drift).

Diagrams must stay readable from the back of a room: HomeFinder's system overview became three rows (requests on top, stores in the middle, updates along the bottom), bigger text, fewer lines, and a final step that fades everything except the point ("Cache first: about 40% of searches never reach the search cluster"). Check every component you talk about is on the diagram.

## 5. PowerPoint rehearsal version

Use the pptx skill. Follow the talk's chapters (HomeFinder: 10 chapters → 12 slides), in the same dark style.
- One point per slide, with the "why X over Y" call on the slide and its own comparison slide for each big push back.
- **Native charts** (bar, stacked bar, 100% stacked bar) for numbers like reads vs writes, the latency budget and the bill, not pictures of charts.
- The full talk track in each slide's speaker notes, so the person rehearses in Presenter View.
- A **cheat sheet** slide near the end: six likely questions, one-line answer each ("Answer in one sentence, then stop").
- Validate the file and render every slide to an image to check for overflow before handing it over.

## 6. Style choice

If the person hasn't fixed a style, make three title-slide previews on one page and ask them to pick (the frontend-slides method, github.com/zarazhangrui/frontend-slides). Build in your recommended style while they choose; switching later is cheap when colors are tokens. Diagram-heavy talks suit a dark "blueprint" or the explorer's warm grey and dark styles.

## 7. Before handing over

1. Step through every stop with the keyboard in a real browser (Playwright): no console errors, no element overflowing the 1920×1080 stage, nothing overlapping at any stop.
2. Time a dry read of the notes against each section's minutes.
3. Check numbers match the explorer, the study notes and the video.
4. Publish as an artifact (private by default), save a copy in project files, and add the HTML to the repo.

## 8. Pitfalls seen

- Steps that reveal one card at a time for content that is really one picture.
- Too much text per card on the slide; the person asked to cut it to short notes.
- A system overview missing a component the talk depends on (the cache).
- Lines on a slide that didn't fit the story; cut them instead of shrinking them.
- Reusing the video scenes but forgetting to remove the speaker bubbles and captions.
