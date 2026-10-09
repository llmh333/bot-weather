"""Đọc vị trí người dùng gửi trên Telegram, lưu lại, rồi gửi thời tiết.

Chạy trên GitHub Actions: không cần LAT/LON cố định.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from weather_core import (
    USER_AGENT,
    fetch_forecast,
    format_report,
    place_from_coords,
    post_telegram,
    quiet_now,
    search_place,
)

DATA_FILE = Path(__file__).with_name("subscribers.json")
HELP = (
    "Gửi vị trí hiện tại, hoặc gõ /city Hải Phòng.\n"
    "Bot nhớ chỗ đó và nhắc mỗi 3 giờ. Muốn đổi chỗ thì gửi vị trí mới.\n\n"
    "/weather — xem ngay\n"
    "/forecast — thêm giờ mọc, lặn\n"
    "/on — bật nhắc\n"
    "/off — tắt nhắc\n"
    "/quiet 22 6 — không nhắc từ 22h đến 6h\n"
    "/quiet off — bỏ giờ im lặng\n"
    "/status — vị trí đang nhớ"
)
LOCATION_KEYBOARD = {
    "keyboard": [[{"text": "Gửi vị trí của tôi", "request_location": True}]],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}
REMOVE_KEYBOARD = {"remove_keyboard": True}


def load_state() -> dict:
    if DATA_FILE.exists():
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}
    data.setdefault("update_offset", 0)
    data.setdefault("users", {})
    return data


def save_state(state: dict) -> None:
    temporary = DATA_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(DATA_FILE)


def seed_from_env(state: dict) -> None:
    chat_id = os.getenv("CHAT_ID", "").strip()
    lat = os.getenv("LAT", "").strip()
    lon = os.getenv("LON", "").strip()
    if not (chat_id and lat and lon) or chat_id in state["users"]:
        return
    user = {
        "chat_id": int(chat_id),
        "lat": float(lat),
        "lon": float(lon),
        "place": os.getenv("PLACE", "").strip() or "vị trí đã lưu",
        "notify": True,
        "timezone": os.getenv("DEFAULT_TIMEZONE", "Asia/Ho_Chi_Minh"),
    }
    quiet_from = os.getenv("QUIET_FROM", "").strip()
    quiet_to = os.getenv("QUIET_TO", "").strip()
    if quiet_from and quiet_to:
        user["quiet_from"] = int(quiet_from)
        user["quiet_to"] = int(quiet_to)
    state["users"][chat_id] = user


def get_updates(token: str, offset: int) -> list[dict]:
    params = {"timeout": 0, "allowed_updates": json.dumps(["message"])}
    if offset:
        params["offset"] = offset
    url = "https://api.telegram.org/bot" + token + "/getUpdates?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode())
    if not body.get("ok"):
        raise RuntimeError(body)
    return body.get("result") or []


def ensure_user(state: dict, chat_id: int) -> dict:
    user = state["users"].setdefault(str(chat_id), {"notify": True})
    user["chat_id"] = chat_id
    return user


def remember_place(user: dict, lat: float, lon: float, place: str) -> None:
    user["lat"] = lat
    user["lon"] = lon
    user["place"] = place
    user["notify"] = True


def send_report(token: str, user: dict, *, detailed: bool = False) -> None:
    data = fetch_forecast(float(user["lat"]), float(user["lon"]))
    if data.get("timezone"):
        user["timezone"] = data["timezone"]
    text = format_report(user.get("place") or "vị trí đã lưu", data, detailed=detailed)
    post_telegram(token, int(user["chat_id"]), text, REMOVE_KEYBOARD)


def apply_message(state: dict, token: str, message: dict, sent: set[int]) -> None:
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return
    user = ensure_user(state, int(chat_id))
    location = message.get("location")
    if location and "latitude" in location and "longitude" in location:
        lat = float(location["latitude"])
        lon = float(location["longitude"])
        place = place_from_coords(lat, lon) or f"{lat:.4f}, {lon:.4f}"
        remember_place(user, lat, lon, place)
        post_telegram(token, int(chat_id), f"Đã nhớ vị trí: {place}. Lần sau gửi vị trí mới nếu bạn đổi chỗ.")
        send_report(token, user)
        sent.add(int(chat_id))
        return

    text = (message.get("text") or "").strip()
    if not text:
        return
    parts = text.split()
    command = parts[0].split("@", 1)[0].lower()
    args = parts[1:]

    if command in {"/start", "/help"}:
        post_telegram(token, int(chat_id), HELP, LOCATION_KEYBOARD)
        return
    if command == "/city":
        name = " ".join(args).strip()
        if not name:
            post_telegram(token, int(chat_id), "Ví dụ: /city Hải Phòng")
            return
        found = search_place(name)
        if not found:
            post_telegram(token, int(chat_id), f"Không tìm thấy «{name}».")
            return
        label = ", ".join(
            part for part in (found.get("name"), found.get("admin1"), found.get("country")) if part
        )
        remember_place(user, float(found["latitude"]), float(found["longitude"]), label)
        post_telegram(token, int(chat_id), f"Đã nhớ: {label}. Gõ /city khác khi muốn đổi.")
        send_report(token, user)
        sent.add(int(chat_id))
        return
    if command == "/off":
        user["notify"] = False
        post_telegram(token, int(chat_id), "Đã tắt nhắc tự động. /on để bật lại.")
        return
    if command == "/on":
        if "lat" not in user:
            post_telegram(token, int(chat_id), "Chưa có vị trí. Gửi vị trí hoặc /city Hải Phòng.", LOCATION_KEYBOARD)
            return
        user["notify"] = True
        post_telegram(token, int(chat_id), "Đã bật nhắc mỗi 3 giờ.")
        return
    if command == "/quiet":
        if not args:
            if user.get("quiet_from") is None:
                post_telegram(token, int(chat_id), "Chưa đặt giờ im lặng. Ví dụ: /quiet 22 6")
            else:
                post_telegram(
                    token,
                    int(chat_id),
                    f"Đang im lặng từ {int(user['quiet_from'])}h đến {int(user['quiet_to'])}h.",
                )
            return
        if args[0].lower() in {"off", "tat", "tắt"}:
            user["quiet_from"] = None
            user["quiet_to"] = None
            post_telegram(token, int(chat_id), "Đã bỏ giờ im lặng.")
            return
        if len(args) != 2:
            post_telegram(token, int(chat_id), "Ví dụ: /quiet 22 6")
            return
        try:
            start, end = int(args[0]), int(args[1])
        except ValueError:
            post_telegram(token, int(chat_id), "Giờ phải là số từ 0 đến 23. Ví dụ: /quiet 22 6")
            return
        if not (0 <= start <= 23 and 0 <= end <= 23) or start == end:
            post_telegram(token, int(chat_id), "Hai giờ khác nhau, từ 0 đến 23.")
            return
        user["quiet_from"] = start
        user["quiet_to"] = end
        post_telegram(token, int(chat_id), f"Không nhắc từ {start}h đến {end}h. /weather vẫn xem được.")
        return
    if command == "/status":
        if "lat" not in user:
            post_telegram(token, int(chat_id), "Chưa nhớ vị trí nào.", LOCATION_KEYBOARD)
            return
        flag = "bật" if user.get("notify", True) else "tắt"
        quiet = (
            "không"
            if user.get("quiet_from") is None
            else f"{int(user['quiet_from'])}h–{int(user['quiet_to'])}h"
        )
        post_telegram(
            token,
            int(chat_id),
            f"Vị trí: {user.get('place')}\nTọa độ: {user['lat']}, {user['lon']}\nNhắc 3 giờ: {flag}\nIm lặng: {quiet}",
        )
        return
    if command in {"/weather", "/forecast"}:
        if "lat" not in user:
            post_telegram(token, int(chat_id), "Chưa có vị trí. Gửi vị trí hoặc /city Hải Phòng.", LOCATION_KEYBOARD)
            return
        send_report(token, user, detailed=command == "/forecast")
        sent.add(int(chat_id))
        return
    if command.startswith("/"):
        post_telegram(token, int(chat_id), HELP, LOCATION_KEYBOARD)


def ingest(state: dict, token: str, sent: set[int]) -> None:
    while True:
        updates = get_updates(token, int(state.get("update_offset") or 0))
        if not updates:
            return
        for update in updates:
            state["update_offset"] = int(update["update_id"]) + 1
            message = update.get("message")
            if message:
                try:
                    apply_message(state, token, message, sent)
                except Exception as exc:
                    print("bỏ qua tin", update.get("update_id"), exc, file=sys.stderr)
        if len(updates) < 100:
            return


def main() -> int:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        print("Thiếu BOT_TOKEN", file=sys.stderr)
        return 1

    state = load_state()
    seed_from_env(state)
    sent: set[int] = set()
    try:
        ingest(state, token, sent)
    except Exception as exc:
        print("Không đọc được tin nhắn Telegram:", exc, file=sys.stderr)
    save_state(state)

    people = [
        user
        for user in state["users"].values()
        if user.get("notify", True) and "lat" in user and int(user["chat_id"]) not in sent
    ]
    if not people and not sent and not any("lat" in user for user in state["users"].values()):
        print(
            "Chưa có vị trí. Trên Telegram hãy gửi vị trí hoặc gõ /city Hải Phòng, rồi chạy lại workflow. Không cần LAT/LON.",
            file=sys.stderr,
        )
        return 1

    failed = 0
    for user in people:
        chat_id = int(user["chat_id"])
        if quiet_now(user):
            print("skip quiet", chat_id)
            continue
        try:
            send_report(token, user)
        except Exception as exc:
            failed += 1
            print("fail", chat_id, exc, file=sys.stderr)
            continue
        print("sent", chat_id)
    save_state(state)
    if failed and not sent and failed == len(people):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
