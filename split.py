"""Split the wide OBS recording into two synchronized tracks.

    python split.py <recording.mkv> [--out <folder>] [--no-camera]

The screen sits top left (up to 1920x1200), the webcam on the right
(1920x1080, centered in its 1920x1200 field). Both outputs carry the same
audio and start at the same instant, so no alignment is needed later.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

FIELD_W, FIELD_H = 1920, 1200
CAMERA_H = 1080
FPS = 30
ENCODE = ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "21", "-b:v", "0", "-pix_fmt", "yuv420p",
          "-movflags", "+faststart"]   # mp4 with the index up front, so players start right away


def ffmpeg() -> str:
    p = shutil.which("ffmpeg")
    if not p:
        raise SystemExit("ffmpeg not found")
    return p


def duration(path: Path) -> float:
    r = subprocess.run([shutil.which("ffprobe") or "ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "json", str(path)], capture_output=True, text=True)
    return float(json.loads(r.stdout)["format"]["duration"])


def freeze_filter(src: str, dst: str, spans: list[tuple[float, float]]) -> str:
    """Filter chain that replaces all frames in each span (seconds) with the frame just before.

    Used for Alt+Tab: the Windows task switcher cannot be excluded from capture,
    so it is covered afterwards while audio and camera keep running.
    """
    if not spans:
        return f"[{src}]null[{dst}]"
    parts, cur = [], src
    for i, (a, b) in enumerate(sorted(spans)):
        first, last = max(1, int(a * FPS)), max(1, int(b * FPS + 0.999))
        nxt = dst if i == len(spans) - 1 else f"fz{i}"
        parts.append(f"[{cur}]split=2[fa{i}][fb{i}];[fa{i}][fb{i}]freezeframes="
                     f"first={first}:last={last}:replace={max(0, first - 2)}[{nxt}]")
        cur = nxt
    return ";".join(parts)


def split_recording(source: Path, screen_out: Path, camera_out: Path | None,
                    progress: Callable[[float], None] | None = None,
                    freeze: list[tuple[float, float]] | None = None,
                    screen_size: tuple[int, int] = (FIELD_W, FIELD_H)) -> None:
    """Write the tracks; progress(0..1) is called while encoding.

    freeze: spans in seconds where the screen track stands still (Alt+Tab).
    screen_size: size of the screen image top left in its field (smaller without taskbar).
    """
    total = duration(source)
    top = (FIELD_H - CAMERA_H) // 2
    sw, sh = screen_size
    frz = freeze_filter("s0", "s", [s for s in (freeze or []) if s[1] > s[0]])
    if camera_out:
        graph = (f"[0:v]split=2[a][b];[a]crop={sw}:{sh}:0:0[s0];{frz};"
                 f"[b]crop={FIELD_W}:{CAMERA_H}:{FIELD_W}:{top}[c]")
        outputs = ["-map", "[s]", "-map", "0:a?", *ENCODE, "-c:a", "copy", str(screen_out),
                   "-map", "[c]", "-map", "0:a?", *ENCODE, "-c:a", "copy", str(camera_out)]
    else:
        graph = f"[0:v]crop={sw}:{sh}:0:0[s0];{frz}"
        outputs = ["-map", "[s]", "-map", "0:a?", *ENCODE, "-c:a", "copy", str(screen_out)]
    screen_out.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.Popen([ffmpeg(), "-y", "-v", "error", "-nostats", "-progress", "pipe:1",
                          "-i", str(source), "-filter_complex", graph, *outputs],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in p.stdout:
        if line.startswith("out_time_us=") and progress and total > 0:
            try:
                progress(min(1.0, int(line.split("=")[1]) / 1e6 / total))
            except ValueError:
                pass
    if p.wait() != 0:
        raise RuntimeError("ffmpeg: " + p.stderr.read()[-800:])
    # cross-check: every track as long as the source (one second tolerance)
    for out in [screen_out] + ([camera_out] if camera_out else []):
        if abs(duration(out) - total) > 1.0:
            raise RuntimeError(f"length mismatch: {out.name}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("recording")
    ap.add_argument("--out")
    ap.add_argument("--no-camera", action="store_true")
    a = ap.parse_args()
    src = Path(a.recording)
    out = Path(a.out) if a.out else src.parent
    screen = out / f"{src.stem} - screen.mp4"
    camera = None if a.no_camera else out / f"{src.stem} - camera.mp4"
    split_recording(src, screen, camera, lambda x: print(f"\r{x:5.0%}", end=""))
    print()
    for p in [screen, camera]:
        if p:
            print(p)
