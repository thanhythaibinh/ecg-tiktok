"""Pipeline: chọn bài -> kịch bản -> giọng đọc -> dựng video -> (đăng TikTok).

  python -m ecgtok.pipeline next            # làm bài kế tiếp chưa làm
  python -m ecgtok.pipeline next --count 7  # làm 7 bài (lịch cả tuần)
  python -m ecgtok.pipeline lesson 11       # làm lại bài 11
  thêm --offline (không gọi Claude), --post (đăng TikTok)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import unicodedata
from datetime import datetime
from pathlib import Path

import yaml

from . import render, script_gen, tts

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state.json"


def slug(s):
    s = unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D"))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:50]


def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {"done": {}}


def build_audio(script, cfg, work: Path) -> tuple[Path, list[float]]:
    wavs, durs = [], []
    for i, sc in enumerate(script["scenes"]):
        mp3 = work / f"s{i}.mp3"
        d = tts.speak(sc["narration"], mp3, cfg["tts"]["voice"], cfg["tts"]["rate"])
        wav = work / f"s{i}.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-af", "apad", "-t", f"{d:.3f}",
                        "-ar", "44100", "-ac", "1", str(wav)], check=True)
        wavs.append(wav)
        durs.append(d)
    lst = work / "list.txt"
    lst.write_text("".join(f"file '{w.name}'\n" for w in wavs))
    voice = work / "voice.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(voice)], check=True)
    return voice, durs


def mux(video: Path, voice: Path, cfg, out: Path):
    music = cfg["video"].get("music")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-i", str(voice)]
    if music and Path(music).exists():
        cmd += ["-stream_loop", "-1", "-i", music, "-filter_complex",
                f"[2:a]volume={cfg['video']['music_volume']}[m];[1:a][m]amix=inputs=2:duration=first[a]",
                "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-map", "0:v", "-map", "1:a"]
    cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)


def make_lesson(lesson, lessons, cfg, use_llm=True, post=False):
    nxt = next((l for l in lessons if l["id"] == lesson["id"] + 1), None)
    out = ROOT / "output" / f"{lesson['id']:02d}-{slug(lesson['title'])}"
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)
    print(f"== Bài {lesson['id']}: {lesson['title']}")

    script = script_gen.generate(lesson, nxt, cfg, use_llm)
    (out / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=2))

    voice, durs = build_audio(script, cfg, work)
    silent = work / "video_silent.mp4"
    render.render_video(script, lesson, durs, len(lessons), cfg, silent)
    final = out / "video.mp4"
    mux(silent, voice, cfg, final)
    render.thumbnail(script, lesson, len(lessons), cfg, out / "cover.jpg")

    caption = script["caption"] + "\n" + " ".join("#" + h.lstrip("#") for h in script["hashtags"])
    (out / "caption.txt").write_text(caption + "\n\n📌 Ghim bình luận: " + script["quiz"] + "\n")
    print(f"   -> {final} ({sum(durs):.1f}s)")

    publish_id = None
    if post or cfg["publish"].get("auto_post"):
        if os.environ.get("TIKTOK_ACCESS_TOKEN") or os.environ.get("TIKTOK_REFRESH_TOKEN"):
            from . import tiktok
            publish_id = tiktok.post_video(final, caption, cfg["publish"]["privacy"])
        else:
            print("   [tiktok] thiếu TIKTOK_ACCESS_TOKEN – bỏ qua bước đăng")
    return {"video": str(final.relative_to(ROOT)), "at": datetime.now().isoformat(timespec="seconds"),
            "llm": use_llm, "publish_id": publish_id}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["next", "lesson"])
    ap.add_argument("id", nargs="?", type=int)
    ap.add_argument("--count", type=int)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="không ghi state.json (dùng cho CI)")
    ap.add_argument("--require-llm", action="store_true", help="dừng nếu thiếu ANTHROPIC_API_KEY")
    a = ap.parse_args()

    if a.require_llm and not a.offline and not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Thiếu ANTHROPIC_API_KEY – thêm secret trong GitHub: Settings → Secrets → Actions")
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    lessons = yaml.safe_load((ROOT / "curriculum.yaml").read_text())["lessons"]
    state = load_state()
    if a.mode == "lesson":
        todo = [l for l in lessons if l["id"] == a.id]
    else:
        todo = [l for l in lessons if str(l["id"]) not in state["done"]][: a.count or cfg["publish"]["per_run"]]
    if not todo:
        print("Hết bài trong curriculum – thêm bài mới vào curriculum.yaml")
        return
    for l in todo:
        state["done"][str(l["id"])] = make_lesson(l, lessons, cfg, not a.offline, a.post)
        if not a.dry_run:
            STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
