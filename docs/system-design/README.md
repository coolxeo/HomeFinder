# System design explorer

`explorer.html` is a single, self-contained page for presenting the HomeFinder system design. Open it in any browser; it works offline (fonts fall back to system faces).

- **Architecture:** an animated diagram. Pick a flow (listing update, search, alert) to watch data move hop by hop. Hover a component to see its connections; click it to drill in.
- **Layers, concepts, who does what:** the system as an isometric layer stack, concept cards and an object-action grid.
- **Walks:** MLS pipeline, the 200 ms search budget, H3 geometry at write time, saved-search alerts, spring peaks. Use ← → to step, Esc to go back.
- **Decisions:** seven trade-offs and the first 90 days.

Components are open source and cloud-agnostic; GCP services are named where a managed option fits. Capacity numbers are assumptions, not sourced figures.

Icons: [Lucide](https://lucide.dev) 0.460 (ISC), inlined.
