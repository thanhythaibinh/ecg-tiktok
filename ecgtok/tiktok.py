"""Đăng video qua TikTok Content Posting API (Direct Post, FILE_UPLOAD).

Cần: app trên developers.tiktok.com có scope `video.publish`, access token của tài khoản
(OAuth) đặt trong biến môi trường TIKTOK_ACCESS_TOKEN.
App chưa được audit chỉ đăng được privacy SELF_ONLY.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import requests

API = "https://open.tiktokapis.com/v2/post/publish"


def _h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}


def access_token() -> str:
    """Access token hết hạn sau 24h: nếu có refresh token + client key/secret thì tự làm mới."""
    rt = os.environ.get("TIKTOK_REFRESH_TOKEN")
    if rt and os.environ.get("TIKTOK_CLIENT_KEY"):
        r = requests.post("https://open.tiktokapis.com/v2/oauth/token/", timeout=30, data={
            "client_key": os.environ["TIKTOK_CLIENT_KEY"], "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
            "grant_type": "refresh_token", "refresh_token": rt})
        r.raise_for_status()
        return r.json()["access_token"]
    return os.environ["TIKTOK_ACCESS_TOKEN"]


def post_video(video: Path, caption: str, privacy: str = "SELF_ONLY") -> str:
    token = access_token()
    size = video.stat().st_size
    chunk = size if size <= 64 * 1024 * 1024 else 10 * 1024 * 1024
    n_chunks = max(1, size // chunk)
    init = requests.post(f"{API}/video/init/", headers=_h(token), timeout=60, json={
        "post_info": {"title": caption[:2200], "privacy_level": privacy,
                      "disable_comment": False, "disable_duet": False, "disable_stitch": False},
        "source_info": {"source": "FILE_UPLOAD", "video_size": size,
                        "chunk_size": chunk, "total_chunk_count": n_chunks},
    })
    init.raise_for_status()
    data = init.json()["data"]
    url, pid = data["upload_url"], data["publish_id"]
    with open(video, "rb") as f:
        for i in range(n_chunks):
            start = i * chunk
            end = size - 1 if i == n_chunks - 1 else start + chunk - 1
            f.seek(start)
            body = f.read(end - start + 1)
            r = requests.put(url, data=body, timeout=300, headers={
                "Content-Type": "video/mp4", "Content-Length": str(len(body)),
                "Content-Range": f"bytes {start}-{end}/{size}"})
            r.raise_for_status()
    for _ in range(30):
        st = requests.post(f"{API}/status/fetch/", headers=_h(token), json={"publish_id": pid}, timeout=30)
        status = st.json().get("data", {}).get("status")
        if status in ("PUBLISH_COMPLETE", "FAILED"):
            print(f"[tiktok] {pid}: {status}")
            break
        time.sleep(10)
    return pid
