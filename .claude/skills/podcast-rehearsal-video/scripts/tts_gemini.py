#!/usr/bin/env python3
"""Voice every line of a two-host script with Gemini TTS, one WAV per line.

Usage:
  GEMINI_API_KEY=... python3 tts_gemini.py script.json out_dir/

script.json:
  {"voices": {"Maya": "Aoede", "Sam": "Charon"},
   "style": "Warm, unhurried podcast conversation.",   # optional; a line may set its own "style"
   "scenes": [{"id": "intro", "lines": [{"s": "Maya", "text": "..."}, ...]}, ...]}

Writes out_dir/<scene>-<nn>.wav and adds "wav" paths to out_dir/lines.json.
One request per line gives exact per-line timing for captions and animation.

The key is read from the environment only. Never write it to a file or commit it.
The model name and response format change over time: check the current Gemini
speech-generation docs if a request fails, and set TTS_MODEL to override.
"""
import base64, hashlib, json, os, struct, sys, time, urllib.request

MODEL = os.environ.get("TTS_MODEL", "gemini-3.8-flash-tts")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"


def pcm_to_wav(pcm, rate=24000, ch=1, bits=16):
    hdr = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack(
        "<IHHIIHH", 16, 1, ch, rate, rate * ch * bits // 8, ch * bits // 8, bits) + b"data" + struct.pack("<I", len(pcm))
    return hdr + pcm


def speak(text, voice, style, key):
    # "text" is spoken verbatim; delivery direction goes in speech_metadata.style.
    part = {"text": text}
    if style:
        part["speech_metadata"] = {"style": style}
    body = {
        "contents": [{"role": "user", "parts": [part]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"voice": voice}},
        },
    }
    req = urllib.request.Request(URL.format(MODEL), data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                part = json.load(r)["candidates"][0]["content"]["parts"][0]["inlineData"]
            data, mime = base64.b64decode(part["data"]), part.get("mimeType", "")
            # Raw PCM ("audio/L16;rate=24000") gets a WAV header; a WAV comes back as is.
            # build_timeline.py reads only the RIFF data chunk, so trailing metadata is never played.
            if data[:4] == b"RIFF":
                return data
            rate = int(mime.split("rate=")[1].split(";")[0]) if "rate=" in mime else 24000
            return pcm_to_wav(data, rate)
        except Exception as e:  # rate limits and transient errors
            wait = 2 ** attempt * 2
            print(f"  retry in {wait}s: {e}", file=sys.stderr)
            time.sleep(wait)
    raise SystemExit("TTS failed after 5 attempts")


def main():
    src, out = sys.argv[1], sys.argv[2]
    key = os.environ.get("GEMINI_API_KEY") or sys.exit("Set GEMINI_API_KEY in the environment")
    spec = json.load(open(src))
    os.makedirs(out, exist_ok=True)
    for sc in spec["scenes"]:
        for n, ln in enumerate(sc["lines"]):
            path = os.path.join(out, f"{sc['id']}-{n:02d}.wav")
            voice, style = spec["voices"][ln["s"]], ln.get("style", spec.get("style", ""))
            # Reuse a WAV only if it was made from the same model, text, voice and style.
            sig = hashlib.sha256(json.dumps([MODEL, ln["text"], voice, style]).encode()).hexdigest()
            stamp = path + ".sha256"
            if not (os.path.exists(path) and os.path.exists(stamp) and open(stamp).read() == sig):
                print(f"{sc['id']} {n}: {ln['s']}")
                open(path, "wb").write(speak(ln["text"], voice, style, key))
                open(stamp, "w").write(sig)
            ln["wav"] = path
    json.dump(spec, open(os.path.join(out, "lines.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
