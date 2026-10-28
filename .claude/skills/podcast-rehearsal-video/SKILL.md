---
name: podcast-rehearsal-video
description: Make a short rehearsal video for a talk or pitch: a two-host podcast script, voiced with text-to-speech, over motion-graphics scenes synced to every line, rendered to a 1080p MP4. Use when someone wants to learn or rehearse a presentation by watching it.
---

# Podcast-style rehearsal video

A 5 to 8 minute video that coaches someone through their talk. Two hosts talk it through: one plays the audience and pushes back, the other is the presenter and answers the way the person should. The scenes animate in step with each line, and captions light up word by word so the viewer can practise saying the lines.

Reference build (HomeFinder): `homefinder-pitch-rehearsal.mp4` (6 min 46 s, 1080p30, 10 chapters), script `pitch-rehearsal-script.md`, and `docs/system-design/explorer-deck.html`, which contains the video's exact scene code and timeline.

Scripts in this skill's folder (when it lives in a repo under `.claude/skills/podcast-rehearsal-video/`):
- `scripts/tts_gemini.py`: one WAV per line with Gemini TTS. Key from `GEMINI_API_KEY`.
- `scripts/build_timeline.py`: joins the lines into one clean voice track and writes the timeline (line start and end times plus per-frame loudness).
- `assets/scenes-template.html`: the scene engine with captions and speaker rings; add one builder per scene.
- `scripts/render.mjs`: drives `window.render(t)` frame by frame in Playwright and pipes the frames into ffmpeg with the audio.

If those files aren't available, rebuild them from the descriptions below.

## 1. Script

- **Hosts:** Maya plays the committee (asks, interrupts, pushes back). Sam is the architect and says the lines the presenter should say. Give each a role label on screen ("plays the committee", "the architect").
- **Length:** about 150 spoken words a minute. 7 minutes is about 1,050 words in 10 chapters of 3 to 6 lines each.
- **Order:** the order the talk will be given. HomeFinder: the opener with the shape of the problem in numbers, the one rule, how data gets in, two "push back: why not X?" chapters, the deep dive, build vs buy, cost, a 20-second close.
- **Every decision gets its "why X over Y"** with a number in it ("Kafka is great at scale we don't have. We have twelve events a second.") and, where it exists, the trigger for revisiting it.
- **Write for the ear.** Short sentences, numbers spelled the way they're said ("p ninety-five", "twenty twenty-four"), no tables, no parentheses, no acronyms the listener can't hear clearly.
- **Pitch it at the person's level.** If they know the platform, skip basics and spend the time on reasoning and phrasing.
- Save the script as markdown (`## 01 · Chapter title`, then `**Maya:** ...` lines) and as `script.json` for the voice step:
  `{"voices": {"Maya": "Aoede", "Sam": "Charon"}, "style": "...", "scenes": [{"id": "intro", "lines": [{"s": "Maya", "text": "..."}]}]}`

## 2. Voices

- Generate **one request per line**. That gives exact start and end times for captions and animation, and lets you regenerate one bad line without touching the rest.
- HomeFinder used `gemini-3.8-flash-tts` with Aoede (Maya) and Charon (Sam). Model names change; check the current docs if a call fails.
- **API keys:** read from an environment variable only. Never write a key into a script, a file, the repo or project memory. If the person pasted a key in chat, use it for the session and tell them to rotate it afterwards.
- **The click bug:** Gemini appends a C2PA provenance record (about 6 KB) to its audio. Joining files as raw bytes plays it as a burst of digital noise at the end of every clip. Read only the samples from the WAV `data` chunk (`build_timeline.py` does), add a 12 ms fade at each edge, then de-ess and normalize loudness (`deesser`, `loudnorm=I=-16:TP=-1.5:LRA=11`). Check the gaps between lines are silent.
- Timing defaults: 3 s before the first line, 0.25 s between lines, 2 s between chapters, 5 s after the last line.

```bash
GEMINI_API_KEY=... python3 scripts/tts_gemini.py script.json build/lines
python3 scripts/build_timeline.py build/lines/lines.json build      # voice.wav, timeline.json, timeline.js
```

## 3. Scenes

One HTML page with a fixed 1920×1080 stage and a pure function `render(t)` that draws the frame at time t. No timers, no CSS transitions, no requestAnimationFrame inside scenes: everything is computed from t, so every frame can be rendered in any order and the same code later becomes a keyboard deck.

- **Layout:** chapter number and title top left, chapter progress dashes top right, the scene in the middle (1728×660 from x 96, y 170), captions along the bottom: speaker avatars on the left with a ring that pulses with the voice loudness, and the current line on the right with words lighting up as they are said.
- **Builders:** `B[sceneId] = el => { create elements once; return (lt, L) => { position them } }`. `lt` is seconds since the scene started and `L[k]` is when line k starts, so each reveal is keyed to what is being said: `sh(card, E(lt, L[1] + 1.2))` brings a card in 1.2 s into line 1.
- **Helpers:** `E(t, start, dur)` is a 0→1 ease-out (cubic) starting at `start`; `sh(el, p, dy)` sets opacity and a small rise. Scenes fade in over 0.9 s starting 1.1 s before their first line, and fade out 0.5 s after their last.
- **Background life:** a dotted grid drifting a few pixels a second and one or two large blurred glows on slow sine paths.
- **Visual language:** dark warm ground, cards with soft shadows, one accent (blue) for chosen and in-flow, one signal (orange) for rejected or edge cases, Lucide icons inlined, a mono face only for numbers. Comparison scenes use CHOSEN / NOT NOW tags with three ticks or crosses each. Charts are simple: bars that grow, a single bar that adds up to 100%.
- **Content:** one idea per scene, the number that proves it, and the push-back answered on screen. Pull wording from the person's study notes so the video, deck and notes say the same thing.

Preview the page in a browser (without `#render` it plays in real time) before rendering.

## 4. Render

```bash
cp assets/scenes-template.html build/scenes.html   # then write the builders
node scripts/render.mjs build/scenes.html build/voice.wav out.mp4
```

`render.mjs` opens the page at 1920×1080, waits for fonts, then for each frame calls `window.render(f / 30)`, screenshots it as JPEG and pipes it to ffmpeg (libx264, CRF 18, yuv420p, AAC 192k, faststart). A 7-minute video is about 12,000 frames; run it in the background. Use `--from` and `--to` to re-render a section while iterating.

After rendering: pull a frame from every chapter with `ffmpeg -ss <t> -i out.mp4 -frames:v 1 f.png` and look at them; check nothing overflows the stage, captions don't collide with scene content, and the audio has no clicks at chapter boundaries.

## 5. Reuse: the same scenes as a keyboard deck

Because frames come from `render(t)`, a deck is the same page plus a list of "stops", the moments where a new box has settled. → tweens t from one stop to the next (750-1900 ms, eased), ← rewinds quickly. Remove the captions and speaker avatars for the deck. See the stepped-presentation-deck skill; HomeFinder's `explorer-deck.html` was built this way in a few minutes.

## 6. Hand-over

- Save the MP4, the script markdown and the audio in the project files; don't commit large media to the repo unless asked.
- Tell the person the length, the chapter list, which voices play whom, and that the figures are assumptions where they are.
- Say plainly if you haven't listened to it end to end. Offer to regenerate any line they flag; per-line audio makes that cheap.
