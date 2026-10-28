# HomeFinder system design

Interview material for the HomeFinder system design: a 30-minute talk plus 30 minutes of Q&A. Section picks: MLS integration and pipeline, a deep dive on geospatial search, and cost optimization.

- `explorer.html`: the interactive explorer. It opens with the committee talk (the same deck as `committee-deck.html`, embedded and stepped with ← →, N for notes, F for full screen), then the talk agenda (three parts, timed), then an animated demo of one listing, decision cards (tech and design choices, with what would make us switch), an animated architecture diagram, the five layers a listing passes through, walks (MLS pipeline, 200 ms search budget, H3 geometry, alerts, cost as a 100% bill), a glossary of every term and acronym, and a "Learn it" panel on every component. Acronyms are spelled out on first use with a hover title. Light and dark mode, plus a notes toggle (helper text is hidden by default).
- `explorer-deck.html`: the pitch video as a keyboard deck, without the audio or speakers. Each → press plays the next reveal from the video and settles; ← steps back, ↑/↓ jump between the ten chapters, F goes full screen. The current step is kept in the URL hash.
- `committee-deck.html`: the version for the architecture committee. Same animated style, 18 chapters timed to the brief (high-level architecture 8 min, geo search deep dive 15 min, cost optimization 7 min, then wrap-up). Adds requirements and targets, a system overview, recommendations, index design and sharding, map pins under 300 ms, freshness and failure modes, cost levers, and risks and compliance. N shows presenter notes with a 30 minute timer.
- `deck.html`: the 22-slide "Blueprint" deck. Press N for speaker notes and T to switch theme.
- `notes/architecture-study-notes.md`: every decision in one line plus the reason.
- `notes/speaker-notes-components.md`: long-form notes per component.
- `notes/speaker-notes-podcast.md` and `notes/podcast.mp3`: a two-voice study podcast, about 20 minutes, voiced with Gemini TTS.

GCP-native but light: managed where the protocol is open, proprietary only behind an adapter. Capacity numbers are assumptions, not sourced figures.

Icons: [Lucide](https://lucide.dev) 0.460 (ISC), inlined.

Design skills used for the visual review live in `.claude/skills/`: `hallmark` (anti-slop rules for layout, motion and copy) and `frontend-design` (Anthropic's frontend design skill). Claude Code picks them up automatically in this repo.
