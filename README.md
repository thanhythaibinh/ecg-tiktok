# ECG Tự Học – workflow tự động cho kênh TikTok

```
curriculum.yaml ─► Claude viết kịch bản ─► edge-tts đọc tiếng Việt ─► vẽ ECG + phụ đề ─► video.mp4 ─► TikTok API
   (32 bài)        (JSON có cấu trúc)       (vi-VN-HoaiMyNeural)       (1080x1920, 30fps)   + caption   (tùy chọn)
```

## Chạy

```bash
pip install -r requirements.txt          # cần ffmpeg
export ANTHROPIC_API_KEY=...             # không có -> kịch bản offline từ curriculum
python -m ecgtok.pipeline next           # làm bài kế tiếp
python -m ecgtok.pipeline next --count 7 # làm trước cả tuần
python -m ecgtok.pipeline lesson 11      # làm lại 1 bài
python -m ecgtok.pipeline next --post    # làm + đăng TikTok
```

Kết quả: `output/<id>-<slug>/` gồm `video.mp4`, `cover.jpg`, `caption.txt` (caption + hashtag + câu quiz để ghim), `script.json`.
Tiến độ lưu ở `state.json`.

## Tự động hằng ngày (GitHub Actions)

1. Đưa thư mục này lên một repo GitHub.
2. Settings → Secrets → thêm `ANTHROPIC_API_KEY` (và các secret TikTok nếu muốn tự đăng).
3. `.github/workflows/daily.yml` chạy 18:07 giờ VN mỗi ngày → video ở tab Actions → Artifacts.

Hoặc cron trên máy: `7 18 * * * cd /đường/dẫn/ecg-tiktok && python -m ecgtok.pipeline next`

## Tự đăng TikTok

- Tạo app ở developers.tiktok.com, bật **Content Posting API**, scope `video.publish`, lấy token qua OAuth.
- Secrets: `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN` (tự làm mới token 24h) hoặc `TIKTOK_ACCESS_TOKEN`.
- Đặt `publish.auto_post: true` trong `config.yaml`.
- App **chưa audit chỉ đăng được `SELF_ONLY`** (riêng tư) → mở công khai thủ công trong app, hoặc nộp audit để đăng công khai.

## Tùy chỉnh

| Muốn | Sửa |
|---|---|
| Thêm bài | `curriculum.yaml` (rhythm: xem `RHYTHMS` trong `ecgtok/ecg.py`) |
| Giọng nam | `tts.voice: vi-VN-NamMinhNeural` |
| Nhạc nền | `video.music: nhac.mp3` |
| Văn phong kịch bản | `SYSTEM` trong `ecgtok/script_gen.py` |

24 kiểu nhịp vẽ sẵn: xoang, chậm/nhanh xoang, QT dài, rung nhĩ, cuồng nhĩ, NTT nhĩ/thất, block AV 1/Wenckebach/Mobitz II/độ 3,
block nhánh phải/trái, SVT, nhanh thất, rung thất, STEMI, ST chênh xuống, tăng/hạ kali, dày thất trái, WPW, viêm màng ngoài tim.

> ⚠️ Nội dung y khoa: nên xem lại `script.json` trước khi đăng công khai. Hình ECG là sóng **tổng hợp minh họa**, không phải bản ghi bệnh nhân thật.
