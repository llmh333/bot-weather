"""Bot Telegram thông báo thời tiết theo vị trí, mỗi 3 giờ."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from weather_core import fetch_forecast, format_report, place_from_coords, quiet_now, search_place

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
NOTIFY_INTERVAL = int(os.getenv("NOTIFY_INTERVAL_SECONDS", "10800"))
DATA_FILE = Path(__file__).with_name("subscribers.json")

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("weather-bot")

HELP = (
    "Bot thời tiết theo vị trí.\n\n"
    "Gửi vị trí hoặc /city Hà Nội. Bot trả lời ngay, rồi nhắc mỗi 3 giờ.\n\n"
    "/weather — xem ngay\n"
    "/forecast — 3 ngày, kèm mọc/lặn và UV\n"
    "/city <tên> — đặt theo tên\n"
    "/on — bật nhắc\n"
    "/off — tắt nhắc\n"
    "/quiet 22 6 — im lặng từ 22h đến 6h\n"
    "/quiet off — bỏ giờ im lặng\n"
    "/status — vị trí đang lưu"
)


def load_db() -> dict:
    if not DATA_FILE.exists():
        return {"users": {}}
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log.warning("subscribers.json hỏng, tạo lại dữ liệu trống")
        return {"users": {}}


def save_db(db: dict) -> None:
    temporary = DATA_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(DATA_FILE)


def upsert_user(chat_id: int, **fields) -> dict:
    db = load_db()
    user = db["users"].setdefault(str(chat_id), {"notify": True})
    user.update(fields)
    user["chat_id"] = chat_id
    save_db(db)
    return user


def location_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("Gửi vị trí của tôi", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def geocode(name: str) -> dict | None:
    return search_place(name)


async def reply_weather(update: Update, user: dict, *, detailed: bool = False) -> None:
    try:
        data = fetch_forecast(user["lat"], user["lon"])
    except Exception as exc:
        log.exception("weather failed")
        await update.message.reply_text(f"Không lấy được thời tiết: {exc}")
        return
    if data.get("timezone"):
        upsert_user(update.effective_chat.id, timezone=data["timezone"])
        user["timezone"] = data["timezone"]
    text = format_report(user.get("place") or "vị trí đã lưu", data, detailed=detailed)
    await update.message.reply_text(text)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP, reply_markup=location_keyboard())


async def on_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    loc = update.message.location
    place = place_from_coords(loc.latitude, loc.longitude) or (
        f"{loc.latitude:.4f}, {loc.longitude:.4f}"
    )
    user = upsert_user(
        update.effective_chat.id,
        lat=loc.latitude,
        lon=loc.longitude,
        place=place,
        notify=True,
    )
    await update.message.reply_text(
        f"Đã lưu: {place}. Thông báo mỗi 3 giờ đang bật.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await reply_weather(update, user)


async def city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    name = " ".join(context.args).strip()
    if not name:
        await update.message.reply_text("Ví dụ: /city Hà Nội")
        return
    try:
        found = geocode(name)
    except Exception as exc:
        await update.message.reply_text(f"Không tìm được địa điểm: {exc}")
        return
    if not found:
        await update.message.reply_text(f"Không tìm thấy «{name}». Thử tên đầy đủ hơn.")
        return
    label = ", ".join(
        part for part in [found.get("name"), found.get("admin1"), found.get("country")] if part
    )
    user = upsert_user(
        update.effective_chat.id,
        lat=found["latitude"],
        lon=found["longitude"],
        place=label,
        notify=True,
    )
    await update.message.reply_text(f"Đã đặt vị trí: {label}. Thông báo mỗi 3 giờ đang bật.")
    await reply_weather(update, user)


def saved_user(update: Update) -> dict | None:
    user = load_db()["users"].get(str(update.effective_chat.id))
    if not user or "lat" not in user:
        return None
    return user


async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = saved_user(update)
    if not user:
        await update.message.reply_text(
            "Chưa có vị trí. Gửi vị trí hoặc dùng /city Hà Nội.",
            reply_markup=location_keyboard(),
        )
        return
    await reply_weather(update, user)


async def forecast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = saved_user(update)
    if not user:
        await update.message.reply_text("Chưa có vị trí. Gửi vị trí hoặc dùng /city Hà Nội.")
        return
    await reply_weather(update, user, detailed=True)


async def turn_on(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not saved_user(update):
        await update.message.reply_text("Hãy gửi vị trí hoặc /city trước.")
        return
    upsert_user(update.effective_chat.id, notify=True)
    await update.message.reply_text("Đã bật thông báo mỗi 3 giờ.")


async def turn_off(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.effective_chat.id) not in load_db()["users"]:
        await update.message.reply_text("Bạn chưa đăng ký.")
        return
    upsert_user(update.effective_chat.id, notify=False)
    await update.message.reply_text("Đã tắt thông báo tự động. /on để bật lại.")


async def quiet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not saved_user(update):
        await update.message.reply_text("Hãy gửi vị trí hoặc /city trước.")
        return
    args = [part.strip() for part in context.args]
    if not args:
        user = saved_user(update)
        if user.get("quiet_from") is None:
            await update.message.reply_text("Chưa đặt giờ im lặng. Ví dụ: /quiet 22 6")
        else:
            await update.message.reply_text(
                f"Đang im lặng từ {int(user['quiet_from'])}h đến {int(user['quiet_to'])}h."
            )
        return
    if args[0].lower() in {"off", "tat", "tắt"}:
        upsert_user(update.effective_chat.id, quiet_from=None, quiet_to=None)
        await update.message.reply_text("Đã bỏ giờ im lặng.")
        return
    if len(args) != 2:
        await update.message.reply_text("Ví dụ: /quiet 22 6")
        return
    try:
        start, end = int(args[0]), int(args[1])
    except ValueError:
        await update.message.reply_text("Giờ phải là số từ 0 đến 23.")
        return
    if not (0 <= start <= 23 and 0 <= end <= 23) or start == end:
        await update.message.reply_text("Dùng hai giờ khác nhau, từ 0 đến 23. Ví dụ: /quiet 22 6")
        return
    upsert_user(update.effective_chat.id, quiet_from=start, quiet_to=end)
    await update.message.reply_text(f"Sẽ không nhắc từ {start}h đến {end}h. /weather vẫn xem được.")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = saved_user(update)
    if not user:
        await update.message.reply_text("Chưa lưu vị trí.")
        return
    flag = "bật" if user.get("notify", True) else "tắt"
    if user.get("quiet_from") is None:
        quiet_text = "không"
    else:
        quiet_text = f"{int(user['quiet_from'])}h–{int(user['quiet_to'])}h"
    await update.message.reply_text(
        f"Vị trí: {user.get('place')}\n"
        f"Tọa độ: {user['lat']}, {user['lon']}\n"
        f"Thông báo 3 giờ: {flag}\n"
        f"Giờ im lặng: {quiet_text}"
    )


async def broadcast(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key, user in list(load_db()["users"].items()):
        if not user.get("notify", True) or "lat" not in user:
            continue
        if quiet_now(user):
            log.info("quiet skip %s", key)
            continue
        try:
            data = fetch_forecast(user["lat"], user["lon"])
            if data.get("timezone"):
                upsert_user(int(key), timezone=data["timezone"])
            text = format_report(user.get("place") or "vị trí đã lưu", data)
            await context.bot.send_message(chat_id=int(key), text=text)
        except Exception:
            log.exception("notify failed for %s", key)


def main() -> None:
    if not BOT_TOKEN or BOT_TOKEN.startswith("123456"):
        raise SystemExit("Thiếu BOT_TOKEN. Copy .env.example thành .env rồi điền token.")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("city", city))
    app.add_handler(CommandHandler("weather", weather))
    app.add_handler(CommandHandler("forecast", forecast))
    app.add_handler(CommandHandler("on", turn_on))
    app.add_handler(CommandHandler("off", turn_off))
    app.add_handler(CommandHandler("quiet", quiet))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.LOCATION, on_location))

    if app.job_queue is None:
        raise SystemExit('Thiếu job-queue. Cài: pip install "python-telegram-bot[job-queue]"')
    app.job_queue.run_repeating(
        broadcast,
        interval=NOTIFY_INTERVAL,
        first=NOTIFY_INTERVAL,
        name="weather-every-3h",
    )
    log.info("Bot đang chạy. Thông báo mỗi %s giây.", NOTIFY_INTERVAL)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
