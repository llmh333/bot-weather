"""Thời tiết Open-Meteo dùng chung cho bot và GitHub Actions. Chỉ thư viện chuẩn."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"
USER_AGENT = "telegram-weather-bot/2.0 (personal weather notifier)"

WMO = {
    0: "Trời quang",
    1: "Ít mây",
    2: "Có mây",
    3: "U ám",
    45: "Sương mù",
    48: "Sương mù đóng băng",
    51: "Mưa phùn nhẹ",
    53: "Mưa phùn",
    55: "Mưa phùn dày",
    56: "Mưa phùn đóng băng nhẹ",
    57: "Mưa phùn đóng băng",
    61: "Mưa nhẹ",
    63: "Mưa vừa",
    65: "Mưa to",
    66: "Mưa đóng băng nhẹ",
    67: "Mưa đóng băng",
    71: "Tuyết nhẹ",
    73: "Tuyết vừa",
    75: "Tuyết dày",
    77: "Hạt tuyết",
    80: "Mưa rào nhẹ",
    81: "Mưa rào",
    82: "Mưa rào mạnh",
    85: "Mưa tuyết nhẹ",
    86: "Mưa tuyết mạnh",
    95: "Dông",
    96: "Dông kèm mưa đá nhẹ",
    99: "Dông kèm mưa đá",
}

WEEKDAYS = ["Thứ hai", "Thứ ba", "Thứ tư", "Thứ năm", "Thứ sáu", "Thứ bảy", "Chủ nhật"]


def search_place(name: str) -> dict | None:
    data = _get_json(
        "https://geocoding-api.open-meteo.com/v1/search",
        {"name": name, "count": 1, "language": "vi", "format": "json"},
    )
    results = data.get("results") or []
    return results[0] if results else None


def describe(code) -> str:
    try:
        return WMO.get(int(code), f"Mã thời tiết {code}")
    except (TypeError, ValueError):
        return "Không rõ"


def _round(value) -> str:
    if value is None:
        return "—"
    return str(int(round(float(value))))


def _mm(value) -> str:
    if value is None:
        return "0"
    amount = float(value)
    if amount < 0.05:
        return "0"
    if amount < 10:
        text = f"{amount:.1f}".rstrip("0").rstrip(".")
        return text or "0"
    return str(int(round(amount)))


def _get_json(url: str, params: dict, attempts: int = 3) -> dict:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(attempts):
        delay = 1.2 * (attempt + 1)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code < 500 and exc.code != 429:
                raise
            if exc.code == 429:
                delay = 5 * (attempt + 1)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(delay)
    raise RuntimeError(f"Không gọi được {url}") from last_error


def fetch_forecast(lat: float, lon: float) -> dict:
    return _get_json(
        "https://api.open-meteo.com/v1/forecast",
        {
            "latitude": lat,
            "longitude": lon,
            "current": ",".join(
                [
                    "temperature_2m",
                    "relative_humidity_2m",
                    "apparent_temperature",
                    "weather_code",
                    "wind_speed_10m",
                    "wind_gusts_10m",
                    "precipitation",
                    "cloud_cover",
                    "is_day",
                ]
            ),
            "hourly": ",".join(
                [
                    "temperature_2m",
                    "apparent_temperature",
                    "precipitation_probability",
                    "precipitation",
                    "weather_code",
                    "wind_speed_10m",
                    "uv_index",
                ]
            ),
            "daily": ",".join(
                [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_sum",
                    "precipitation_probability_max",
                    "sunrise",
                    "sunset",
                    "uv_index_max",
                    "wind_speed_10m_max",
                ]
            ),
            "forecast_days": 3,
            "timezone": "auto",
        },
    )


def place_from_coords(lat: float, lon: float) -> str | None:
    try:
        data = _get_json(
            "https://nominatim.openstreetmap.org/reverse",
            {
                "lat": lat,
                "lon": lon,
                "format": "json",
                "accept-language": "vi",
            },
            attempts=1,
        )
    except Exception:
        return None
    address = data.get("address") or {}
    parts: list[str] = []
    for key in ("suburb", "quarter", "village", "town", "city"):
        raw = address.get(key)
        if not raw:
            continue
        name = raw
        for prefix in ("Thành phố ", "Tỉnh ", "Thị xã "):
            if name.startswith(prefix):
                name = name[len(prefix) :]
        if name not in parts:
            parts.append(name)
        if len(parts) == 2:
            break
    if not parts and data.get("display_name"):
        return str(data["display_name"]).split(",")[0][:80]
    return ", ".join(parts)[:80] or None


def _zone(data: dict) -> ZoneInfo:
    name = data.get("timezone") or DEFAULT_TIMEZONE
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)


def _now(data: dict) -> datetime:
    current = (data.get("current") or {}).get("time")
    zone = _zone(data)
    if current:
        try:
            return datetime.fromisoformat(current).replace(tzinfo=zone)
        except ValueError:
            pass
    return datetime.now(zone)


def _hourly_from(data: dict, start: datetime) -> list[dict]:
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    rows = []
    for index, stamp in enumerate(times):
        try:
            moment = datetime.fromisoformat(stamp)
        except ValueError:
            continue
        if moment < start.replace(tzinfo=None):
            continue
        def at(key: str):
            values = hourly.get(key) or []
            return values[index] if index < len(values) else None

        rows.append(
            {
                "time": moment,
                "temp": at("temperature_2m"),
                "apparent": at("apparent_temperature"),
                "pop": at("precipitation_probability"),
                "rain": at("precipitation"),
                "code": at("weather_code"),
                "wind": at("wind_speed_10m"),
                "uv": at("uv_index"),
            }
        )
    return rows


def _alerts(data: dict) -> list[str]:
    current = data.get("current") or {}
    upcoming = _hourly_from(data, _now(data))[:3]
    notes: list[str] = []
    codes = [current.get("weather_code")] + [row["code"] for row in upcoming]
    if any(code is not None and int(code) >= 95 for code in codes):
        notes.append("Có dông trong vài giờ tới")
    elif any(code is not None and int(code) in (65, 67, 82) for code in codes):
        notes.append("Mưa to trong vài giờ tới")
    pops = [row["pop"] for row in upcoming if row["pop"] is not None]
    rain = sum(float(row["rain"] or 0) for row in upcoming)
    if pops and max(pops) >= 70:
        notes.append(f"Khả năng mưa {int(max(pops))}% trong 3 giờ tới")
    elif rain >= 4:
        notes.append(f"Mưa khoảng {_mm(rain)} mm trong 3 giờ tới")
    apparent = current.get("apparent_temperature")
    temperature = current.get("temperature_2m")
    if (apparent is not None and float(apparent) >= 38) or (
        temperature is not None and float(temperature) >= 35
    ):
        notes.append("Nắng nóng, hạn chế ra ngoài lâu")
    gust = current.get("wind_gusts_10m")
    if gust is not None and float(gust) >= 40:
        notes.append(f"Gió giật {_round(gust)} km/h")
    return notes


def _advice(data: dict) -> str | None:
    current = data.get("current") or {}
    upcoming = _hourly_from(data, _now(data))[:6]
    daily = data.get("daily") or {}
    tips: list[str] = []
    pops = [row["pop"] for row in upcoming if row["pop"] is not None]
    if pops and max(pops) >= 50:
        tips.append("Nên mang ô")
    temperature = current.get("temperature_2m")
    if temperature is not None and float(temperature) >= 33:
        tips.append("Uống nước, tránh nắng gắt")
    elif temperature is not None and float(temperature) <= 18:
        tips.append("Trời mát, nên mặc thêm áo")
    uv_values = (daily.get("uv_index_max") or [None])
    uv = uv_values[0] if uv_values else None
    if uv is not None and float(uv) >= 7 and current.get("is_day"):
        tips.append(f"UV cao ({_round(uv)}), hạn chế nắng giữa trưa")
    wind = current.get("wind_speed_10m")
    if wind is not None and float(wind) >= 30:
        tips.append("Gió mạnh, cẩn thận khi đi xe")
    if not tips:
        return None
    return ". ".join(tips[:2]) + "."


def _day_lines(data: dict, detailed: bool) -> list[str]:
    daily = data.get("daily") or {}
    times = daily.get("time") or []
    today = _now(data).date()
    lines = []
    for index, stamp in enumerate(times[:3]):
        day = datetime.fromisoformat(stamp).date()
        if day == today:
            label = "Hôm nay"
        elif day == today + timedelta(days=1):
            label = "Ngày mai"
        else:
            label = WEEKDAYS[day.weekday()]

        def at(key: str):
            values = daily.get(key) or []
            return values[index] if index < len(values) else None

        line = (
            f"{label}: {_round(at('temperature_2m_min'))}–{_round(at('temperature_2m_max'))}°C"
            f" · {describe(at('weather_code'))}"
            f" · mưa {_round(at('precipitation_probability_max'))}% ({_mm(at('precipitation_sum'))} mm)"
            f" · UV {_round(at('uv_index_max'))}"
        )
        if detailed:
            sunrise = str(at("sunrise") or "")
            sunset = str(at("sunset") or "")
            line += f" · mọc {sunrise[11:16]} lặn {sunset[11:16]}"
        lines.append(line)
    return lines


def format_report(place: str, data: dict, *, detailed: bool = False) -> str:
    current = data.get("current") or {}
    moment = _now(data)
    lines = [
        f"Thời tiết tại {place}",
        (
            f"{describe(current.get('weather_code'))} · {_round(current.get('temperature_2m'))}°C"
            f" (cảm giác {_round(current.get('apparent_temperature'))}°C)"
        ),
        (
            f"Độ ẩm {_round(current.get('relative_humidity_2m'))}%"
            f" · gió {_round(current.get('wind_speed_10m'))} km/h"
            f" · mây {_round(current.get('cloud_cover'))}%"
        ),
    ]
    alerts = _alerts(data)
    if alerts:
        lines.append("")
        lines.extend(f"Cảnh báo: {note}" for note in alerts)

    hours = _hourly_from(data, moment + timedelta(hours=1))[:6]
    if hours:
        lines.append("")
        lines.append("6 giờ tới:")
        for row in hours:
            extra = ""
            if row["pop"] is not None and float(row["pop"]) >= 30:
                extra = f" · mưa {int(row['pop'])}%"
            lines.append(f"{row['time'].hour}h {_round(row['temp'])}°C · {describe(row['code'])}{extra}")

    day_lines = _day_lines(data, detailed)
    if day_lines:
        lines.append("")
        lines.extend(day_lines)

    advice = _advice(data)
    if advice:
        lines.append("")
        lines.append(advice)
    lines.append(f"Cập nhật {moment.strftime('%H:%M %d/%m/%Y')}")
    return "\n".join(lines)


def quiet_now(user: dict, timezone_name: str | None = None, moment: datetime | None = None) -> bool:
    start = user.get("quiet_from")
    end = user.get("quiet_to")
    if start is None or end is None:
        return False
    start, end = int(start), int(end)
    if start == end:
        return False
    name = timezone_name or user.get("timezone") or DEFAULT_TIMEZONE
    try:
        zone = ZoneInfo(name)
    except Exception:
        zone = ZoneInfo(DEFAULT_TIMEZONE)
    hour = (moment or datetime.now(zone)).astimezone(zone).hour
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def post_telegram(token: str, chat_id: int, text: str) -> None:
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = json.loads(response.read().decode())
            if not body.get("ok"):
                raise RuntimeError(body)
            return
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.2 * (attempt + 1))
    raise RuntimeError("Không gửi được Telegram") from last_error
