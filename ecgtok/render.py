"""Dựng video dọc 1080x1920: dải ECG trên giấy kẻ ô + chữ + phụ đề, mã hóa bằng ffmpeg."""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import ecg

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
BG = (13, 20, 38)
PAPER = (255, 244, 240)
GRID_S = (247, 200, 200)
GRID_L = (228, 132, 132)
TRACE = (25, 25, 30)
ACCENT = (255, 205, 60)

STRIP_X, STRIP_Y, STRIP_W, STRIP_H = 40, 690, 1000, 550
SECONDS = 4.0
PX_S = STRIP_W / SECONDS       # 250 px/s  -> 10 px = 1 mm ở 25 mm/s
PX_MV = 100                    # 10 mm/mV
BASELINE = STRIP_Y + 380


def font(size, bold=False):
    return ImageFont.truetype(FONT_B if bold else FONT, size)


def _wrap(draw, text, fnt, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=fnt) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _center(draw, lines, y, fnt, fill, gap=12, stroke=0):
    for ln in lines:
        w = draw.textlength(ln, font=fnt)
        draw.text(((1080 - w) / 2, y), ln, font=fnt, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0))
        y += fnt.size + gap
    return y


def _paper(img):
    d = ImageDraw.Draw(img)
    d.rectangle([STRIP_X, STRIP_Y, STRIP_X + STRIP_W, STRIP_Y + STRIP_H], fill=PAPER)
    for i in range(0, STRIP_W + 1, 10):
        d.line([STRIP_X + i, STRIP_Y, STRIP_X + i, STRIP_Y + STRIP_H], fill=GRID_L if i % 50 == 0 else GRID_S,
               width=2 if i % 50 == 0 else 1)
    for j in range(0, STRIP_H + 1, 10):
        y = BASELINE - ((BASELINE - STRIP_Y) // 10) * 10 + j
        if STRIP_Y <= y <= STRIP_Y + STRIP_H:
            d.line([STRIP_X, y, STRIP_X + STRIP_W, y], fill=GRID_L if (y - BASELINE) % 50 == 0 else GRID_S,
                   width=2 if (y - BASELINE) % 50 == 0 else 1)


def _points(strip):
    pts = []
    for t, v in zip(strip.t[::2], strip.y[::2]):
        x = STRIP_X + t * PX_S
        if x > STRIP_X + STRIP_W:
            break
        y = min(max(BASELINE - v * PX_MV, STRIP_Y + 4), STRIP_Y + STRIP_H - 4)
        pts.append((x, y))
    return pts


class SceneArt:
    def __init__(self, scene, header, lesson):
        self.strip = ecg.build(scene["rhythm"], scene["heart_rate"])
        self.pts = _points(self.strip)
        base = Image.new("RGB", (1080, 1920), BG)
        d = ImageDraw.Draw(base)
        d.rounded_rectangle([40, 90, 1040, 160], 20, fill=(32, 46, 80))
        d.text((70, 105), header, font=font(34, True), fill=ACCENT)
        y = _center(d, _wrap(d, lesson["title"], font(62, True), 960), 200, font(62, True), (255, 255, 255))
        _center(d, _wrap(d, scene["on_screen"], font(50, True), 960)[:2], max(y + 30, 470), font(50, True), ACCENT)
        _paper(base)
        lead = lesson.get("lead", "DII")
        d.text((STRIP_X + 14, STRIP_Y + 10), lead, font=font(38, True), fill=(160, 30, 30))
        d.text((STRIP_X + STRIP_W - 330, STRIP_Y + STRIP_H - 40), "25 mm/s · 10 mm/mV", font=font(26), fill=(150, 70, 70))
        self.base = base
        self.hl = scene.get("highlight", "none")
        self.label = scene.get("label", "")
        self.key = (scene["rhythm"], scene["heart_rate"])

    def frame(self, reveal: float, subtitle: list[str], progress: float, disclaimer: str):
        img = self.base.copy()
        d = ImageDraw.Draw(img, "RGBA")
        span = self.strip.ann.get(self.hl) if reveal >= 1 else None
        if span:
            x0, x1 = (STRIP_X + span[0] * PX_S, STRIP_X + span[1] * PX_S)
            d.rectangle([x0, STRIP_Y + 60, x1, STRIP_Y + STRIP_H - 50], fill=(255, 200, 0, 90), outline=(230, 150, 0, 255), width=4)
            if self.label:
                f = font(34, True)
                w = d.textlength(self.label, font=f)
                lx = min(max((x0 + x1) / 2 - w / 2, STRIP_X + 8), STRIP_X + STRIP_W - w - 8)
                d.rounded_rectangle([lx - 12, STRIP_Y + 8, lx + w + 12, STRIP_Y + 56], 10, fill=(230, 150, 0, 255))
                d.text((lx, STRIP_Y + 12), self.label, font=f, fill=(20, 20, 20))
        n = max(2, int(len(self.pts) * min(reveal, 1)))
        d.line(self.pts[:n], fill=TRACE, width=4, joint="curve")
        if reveal < 1:
            hx, hy = self.pts[n - 1]
            d.ellipse([hx - 9, hy - 9, hx + 9, hy + 9], fill=(220, 40, 40))
        _center(d, subtitle, 1320, font(56, True), (255, 255, 255), stroke=4)
        _center(d, [disclaimer], 1800, font(26), (140, 150, 170))
        d.rectangle([0, 1908, int(1080 * progress), 1920], fill=ACCENT)
        return img


def _chunks(text):
    d = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    return _wrap(d, text, font(56, True), 960) or [""]


def render_video(script, lesson, durations, total_lessons, cfg, out_mp4: Path):
    fps = cfg["video"]["fps"]
    header = f"{cfg['channel']['name'].upper()} · BÀI {lesson['id']}/{total_lessons}"
    total = sum(durations)
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1080x1920",
         "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", str(out_mp4)], stdin=subprocess.PIPE)
    elapsed, prev_key = 0.0, None
    for scene, dur in zip(script["scenes"], durations):
        art = SceneArt(scene, header, lesson)
        animate = art.key != prev_key
        prev_key = art.key
        lines = _chunks(scene["narration"])
        weights = [len(x) for x in lines]
        # mỗi chunk phụ đề = 2 dòng
        groups = [lines[i:i + 2] for i in range(0, len(lines), 2)]
        gw = [sum(weights[i:i + 2]) for i in range(0, len(lines), 2)]
        bounds, acc = [], 0
        for w in gw:
            acc += w
            bounds.append(acc / sum(gw) * dur)
        cache_key, cache = None, None
        for f in range(int(round(dur * fps))):
            t = f / fps
            reveal = min(1.0, t / 1.8) if animate else 1.0
            gi = next((i for i, b in enumerate(bounds) if t < b), len(groups) - 1)
            prog = round((elapsed + t) / total, 3)
            key = (round(reveal, 3), gi, prog)
            if key != cache_key:
                cache = art.frame(reveal, groups[gi], (elapsed + t) / total, cfg["channel"]["disclaimer"]).tobytes()
                cache_key = key
            proc.stdin.write(cache)
        elapsed += dur
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg encode lỗi")


def thumbnail(script, lesson, total_lessons, cfg, path: Path):
    art = SceneArt(script["scenes"][0] | {"highlight": "none"}, f"{cfg['channel']['name'].upper()} · BÀI {lesson['id']}/{total_lessons}", lesson)
    art.frame(1.0, [], 0, cfg["channel"]["disclaimer"]).save(path, quality=90)
