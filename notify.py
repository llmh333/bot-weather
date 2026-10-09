"""Gửi một lượt thời tiết. Dùng cho GitHub Actions, không cần thư viện ngoài."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from weather_core import fetch_forecast, format_report, post_telegram, quiet_now

DATA_FILE = Path(__file__).with_name("subscribers.json")


def recipients() -> list[dict]:
    raw = os.getenv("SUBSCRIBERS_JSON", "").strip()
    if raw:
        data = json.loads(raw)
        users = data["users"] if isinstance(data, dict) and "users" in data else data
        rows = list(users.values()) if isinstance(users, dict) else list(users)
        return [user for user in rows if user.get("notify", True) and "lat" in user]

    if DATA_FILE.exists():
        db = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return [
            user
            for user in db.get("users", {}).values()
            if user.get("notify", True) and "lat" in user
        ]

    chat_id = os.getenv("CHAT_ID", "").strip()
    lat = os.getenv("LAT", "").strip()
    lon = os.getenv("LON", "").strip()
    if not (chat_id and lat and lon):
        return []
    user = {
        "chat_id": int(chat_id),
        "lat": float(lat),
        "lon": float(lon),
        "place": os.getenv("PLACE", "vị trí đã lưu"),
        "notify": True,
        "timezone": os.getenv("DEFAULT_TIMEZONE", "Asia/Ho_Chi_Minh"),
    }
    quiet_from = os.getenv("QUIET_FROM", "").strip()
    quiet_to = os.getenv("QUIET_TO", "").strip()
    if quiet_from and quiet_to:
        user["quiet_from"] = int(quiet_from)
        user["quiet_to"] = int(quiet_to)
    return [user]


def main() -> int:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        print("Thiếu BOT_TOKEN", file=sys.stderr)
        return 1
    people = recipients()
    if not people:
        print("Chưa có người nhận. Đặt CHAT_ID, LAT, LON hoặc SUBSCRIBERS_JSON.", file=sys.stderr)
        return 1

    sent = 0
    failed = 0
    for user in people:
        chat_id = int(user["chat_id"])
        if quiet_now(user):
            print("skip quiet", chat_id)
            continue
        try:
            data = fetch_forecast(float(user["lat"]), float(user["lon"]))
            text = format_report(user.get("place") or "vị trí đã lưu", data)
            post_telegram(token, chat_id, text)
        except Exception as exc:
            failed += 1
            print("fail", chat_id, exc, file=sys.stderr)
            continue
        sent += 1
        print("sent", chat_id)
    if sent == 0 and failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
