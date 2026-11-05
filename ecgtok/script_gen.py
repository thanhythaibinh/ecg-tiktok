"""Sinh kịch bản video bằng Claude (structured output). Có fallback offline từ curriculum."""
from __future__ import annotations

import json

from .ecg import HIGHLIGHTS, RHYTHMS

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "narration": {"type": "string"},
                    "on_screen": {"type": "string"},
                    "rhythm": {"type": "string", "enum": RHYTHMS},
                    "heart_rate": {"type": "integer"},
                    "highlight": {"type": "string", "enum": HIGHLIGHTS},
                    "label": {"type": "string"},
                },
                "required": ["narration", "on_screen", "rhythm", "heart_rate", "highlight", "label"],
                "additionalProperties": False,
            },
        },
        "quiz": {"type": "string"},
        "caption": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "scenes", "quiz", "caption", "hashtags"],
    "additionalProperties": False,
}

SYSTEM = """Bạn là bác sĩ tim mạch kiêm biên kịch TikTok cho kênh "{channel}" dạy tự học điện tâm đồ (ECG) bằng tiếng Việt.
Viết kịch bản video dọc 45–70 giây cho người mới (sinh viên y, điều dưỡng).

Yêu cầu:
- 5–7 cảnh. Cảnh 1 là HOOK ≤ 2 câu, gây tò mò (câu hỏi, tình huống lâm sàng, sai lầm hay gặp).
- Mỗi cảnh: narration 1–3 câu ngắn, văn nói tự nhiên, đọc được bằng TTS (viết số và đơn vị thành chữ khi cần: "không phẩy hai giây").
- on_screen: chữ hiển thị ≤ 8 từ, ý chính của cảnh.
- rhythm/heart_rate/highlight: chọn dải ECG minh họa đúng ý cảnh; label = nhãn ngắn cho vùng highlight (vd "PR 0,32 s").
- Chính xác y khoa tuyệt đối theo khuyến cáo hiện hành; không đưa liều thuốc; không khẳng định chẩn đoán cho người xem.
- Cảnh cuối: tóm tắt 1 câu + kêu gọi follow để học bài tiếp theo.
- quiz: 1 câu hỏi trắc nghiệm ngắn để ghim ở bình luận.
- caption ≤ 150 ký tự, hashtags 5–8 cái (không dấu #), gồm #ecg #dientamdo.
"""


def _lesson_prompt(lesson: dict, nxt: dict | None) -> str:
    return (
        f"Bài {lesson['id']}: {lesson['title']}\n"
        f"Chuyển đạo minh họa: {lesson.get('lead', 'DII')}; nhịp gợi ý: {lesson['rhythm']} {lesson.get('hr', 75)} l/ph\n"
        "Ý chính bắt buộc:\n- " + "\n- ".join(lesson["points"]) +
        (f"\nBài tiếp theo: {nxt['title']}" if nxt else "")
    )


def generate_llm(lesson, nxt, cfg) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    resp = client.beta.messages.create(
        model=cfg["llm"]["model"],
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": cfg["llm"].get("effort", "medium"),
                       "format": {"type": "json_schema", "schema": SCHEMA}},
        system=SYSTEM.format(channel=cfg["channel"]["name"]),
        messages=[{"role": "user", "content": _lesson_prompt(lesson, nxt)}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"Model từ chối: {resp.stop_details}")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def generate_offline(lesson, nxt, cfg) -> dict:
    """Kịch bản dựng sẵn từ các ý chính – dùng khi không có API key."""
    r, hr, hl = lesson["rhythm"], lesson.get("hr", 75), lesson.get("highlight", "none")
    scenes = [{"narration": f"Bạn có nhận ra trên điện tâm đồ: {lesson['title'].lower().rstrip('?')} không? Xem ngay sau đây.",
               "on_screen": lesson["title"], "rhythm": r, "heart_rate": hr, "highlight": "none", "label": ""}]
    for pt in lesson["points"]:
        scenes.append({"narration": pt + ".", "on_screen": pt[:48], "rhythm": r, "heart_rate": hr,
                       "highlight": hl, "label": hl.upper() if hl != "none" else ""})
    tail = f" Bài sau: {nxt['title']}." if nxt else ""
    scenes.append({"narration": f"Lưu video lại để ôn, follow kênh để học tiếp.{tail}",
                   "on_screen": "Follow để học tiếp", "rhythm": r, "heart_rate": hr, "highlight": "none", "label": ""})
    return {"title": lesson["title"], "scenes": scenes,
            "quiz": f"Câu hỏi: {lesson['points'][0]} – đúng hay sai?",
            "caption": f"Bài {lesson['id']}: {lesson['title']} | Tự học ECG mỗi ngày",
            "hashtags": ["ecg", "dientamdo", "yhoc", "sinhvienyk", "dieuduong", "hoccungtiktok"]}


def generate(lesson, nxt, cfg, use_llm=True) -> dict:
    if use_llm:
        try:
            return generate_llm(lesson, nxt, cfg)
        except Exception as e:  # thiếu key / lỗi mạng -> offline
            print(f"[script] LLM lỗi ({type(e).__name__}: {e}); dùng kịch bản offline")
    return generate_offline(lesson, nxt, cfg)
