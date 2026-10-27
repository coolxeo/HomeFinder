# HomeFinder system design

Interview material for the HomeFinder system design: a 30-minute talk plus 30 minutes of Q&A. Section picks: MLS integration and pipeline, a deep dive on geospatial search, and cost optimization.

- `explorer.html`: the interactive explorer. It has decision cards (tech and design choices), an animated architecture diagram, "How a listing moves" in five layers, walks (MLS pipeline, 200 ms search budget, H3 geometry, alerts, cost as a 100% bill) and a "Learn it" panel on every component. Light and dark mode, plus a notes toggle (helper text is hidden by default).
- `deck.html`: the 22-slide "Blueprint" deck. Press N for speaker notes and T to switch theme.
- `notes/architecture-study-notes.md`: every decision in one line plus the reason.
- `notes/speaker-notes-components.md`: long-form notes per component.
- `notes/speaker-notes-podcast.md` and `notes/podcast.mp3`: a two-voice study podcast, about 20 minutes, voiced with Gemini TTS.

GCP-native but light: managed where the protocol is open, proprietary only behind an adapter. Capacity numbers are assumptions, not sourced figures.

Icons: [Lucide](https://lucide.dev) 0.460 (ISC), inlined.
