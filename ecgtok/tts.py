"""Giọng đọc tiếng Việt qua edge-tts; fallback: âm thanh im lặng theo độ dài ước tính."""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def _silent(path: Path, secs: float):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                    "-t", f"{secs:.2f}", "-q:a", "9", str(path)], check=True)


def speak(text: str, path: Path, voice: str, rate: str) -> float:
    try:
        import edge_tts

        asyncio.run(edge_tts.Communicate(text, voice, rate=rate).save(str(path)))
        if path.stat().st_size < 1000:
            raise RuntimeError("audio rỗng")
    except Exception as e:
        est = max(2.0, len(text) / 14.0)
        print(f"[tts] edge-tts lỗi ({type(e).__name__}); dùng âm thanh im lặng {est:.1f}s")
        _silent(path, est)
    return duration(path) + 0.35  # nghỉ ngắn giữa các cảnh
