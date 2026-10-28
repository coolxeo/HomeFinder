#!/usr/bin/env python3
"""Join per-line voice files into one clean track and a timeline for the scenes.

Usage:
  python3 build_timeline.py lines.json out_dir/ [--fps 30] [--lead 3] [--scene-gap 2] [--line-gap 0.25] [--tail 5]

Reads lines.json from tts_gemini.py (every line has "wav"). Writes:
  out_dir/voice.wav       48 kHz mono, de-essed and loudness-normalized
  out_dir/timeline.js     the same timeline as `window.TL = {...}` for the scenes page
  out_dir/timeline.json   {"fps", "scenes": [{"id", "t0", "dur", "lines": [{"s", "text", "t0", "t1"}]}],
                           "env": [per-frame loudness 0..1], "total"}

Why the RIFF parsing: Gemini appends a C2PA content credential (a few KB) to its
audio. Concatenating files as raw bytes plays that metadata as a burst of noise at
the end of every clip. Only the samples in the "data" chunk are used here.
"""
import argparse, json, os, struct, subprocess, sys
import numpy as np

SR = 48000


def read_wav_samples(path):
    """Return float32 mono samples at the file's rate, from the RIFF data chunk only."""
    b = open(path, "rb").read()
    if b[:4] != b"RIFF" or b[8:12] != b"WAVE":
        sys.exit(f"{path}: not a WAV file")
    pos, fmt, data = 12, None, None
    while pos + 8 <= len(b):
        cid, size = b[pos:pos + 4], struct.unpack("<I", b[pos + 4:pos + 8])[0]
        body = b[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            fmt = struct.unpack("<HHIIHH", body[:16])
        elif cid == b"data":
            data = body
            break  # anything after the data chunk (C2PA, LIST, id3) is ignored
        pos += 8 + size + (size & 1)
    if not fmt or data is None:
        sys.exit(f"{path}: missing fmt or data chunk")
    tag, ch, rate, _, _, bits = fmt
    if tag != 1 or bits != 16:
        sys.exit(f"{path}: expected 16-bit PCM, got format {tag} / {bits} bits")
    x = np.frombuffer(data[: len(data) // (2 * ch) * 2 * ch], dtype="<i2").astype(np.float32) / 32768
    return x.reshape(-1, ch).mean(axis=1), rate


def resample(x, rate):
    if rate == SR:
        return x
    n = int(round(len(x) * SR / rate))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def fade(x, ms=12):
    n = min(len(x) // 2, int(SR * ms / 1000))
    if n:
        r = np.linspace(0, 1, n, dtype=np.float32)
        x[:n] *= r
        x[-n:] *= r[::-1]
    return x


def check_tail(x, path):
    """Warn if the last 80 ms are loud and noisy, the signature of metadata played as audio."""
    t = x[-int(SR * .08):]
    rms = float(np.sqrt(np.mean(t ** 2))) if len(t) else 0
    zc = float(np.mean(np.abs(np.diff(np.sign(t))) > 0)) if len(t) > 1 else 0
    if rms > .05 and zc > .3:
        print(f"warning: {path} ends in loud broadband noise (rms {rms:.2f}); listen to it", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lines"), ap.add_argument("out")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--lead", type=float, default=3.0)
    ap.add_argument("--scene-gap", type=float, default=2.0)
    ap.add_argument("--line-gap", type=float, default=0.25)
    ap.add_argument("--tail", type=float, default=5.0)
    a = ap.parse_args()
    spec = json.load(open(a.lines))
    os.makedirs(a.out, exist_ok=True)

    parts, t, scenes = [np.zeros(int(SR * a.lead), np.float32)], a.lead, []
    for si, sc in enumerate(spec["scenes"]):
        if si:
            parts.append(np.zeros(int(SR * a.scene_gap), np.float32)); t += a.scene_gap
        s0, lines = t, []
        for li, ln in enumerate(sc["lines"]):
            x, rate = read_wav_samples(ln["wav"])
            x = fade(resample(x, rate))
            check_tail(x, ln["wav"])
            gap = a.line_gap if li < len(sc["lines"]) - 1 else 0
            parts += [x, np.zeros(int(SR * gap), np.float32)]
            dur = len(x) / SR
            lines.append({"s": ln["s"], "text": ln["text"], "t0": round(t, 3), "t1": round(t + dur, 3)})
            t += dur + gap
        scenes.append({"id": sc["id"], "t0": round(s0, 3), "dur": round(t - s0, 3), "lines": lines})
    parts.append(np.zeros(int(SR * a.tail), np.float32)); t += a.tail
    y = np.concatenate(parts)

    raw = os.path.join(a.out, "voice.raw.wav")
    pcm = (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()
    open(raw, "wb").write(b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " +
                          struct.pack("<IHHIIHH", 16, 1, 1, SR, SR * 2, 2, 16) + b"data" + struct.pack("<I", len(pcm)) + pcm)
    voice = os.path.join(a.out, "voice.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-af",
                    "deesser=i=0.4,loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", str(SR), "-ac", "1", voice], check=True)
    os.remove(raw)

    # Per-frame loudness from the final track: drives the speaker ring pulse.
    z, _ = read_wav_samples(voice)
    hop = SR // a.fps
    frames = int(np.ceil(len(z) / hop))
    env = np.array([np.sqrt(np.mean(z[i * hop:(i + 1) * hop] ** 2)) if i * hop < len(z) else 0 for i in range(frames)])
    env = np.clip(env / (np.percentile(env[env > 0], 95) if np.any(env > 0) else 1), 0, 1)

    tl = {"fps": a.fps, "scenes": scenes, "env": [round(float(v), 3) for v in env], "total": round(t, 3)}
    json.dump(tl, open(os.path.join(a.out, "timeline.json"), "w"))
    # Same data as a script tag, so a page opened from file:// can load it without fetch.
    open(os.path.join(a.out, "timeline.js"), "w").write("window.TL = " + json.dumps(tl) + ";\n")
    print(f"{len(scenes)} scenes, {sum(len(s['lines']) for s in scenes)} lines, {t:.1f} s -> {voice}")


if __name__ == "__main__":
    main()
