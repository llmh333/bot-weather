# Bot Telegram thông báo thời tiết mỗi 3 giờ

Bot nhận vị trí, trả thời tiết ngay (hiện tại, 6 giờ tới, 3 ngày, cảnh báo mưa/nắng), rồi tự nhắc mỗi 3 giờ.

Nguồn: [Open-Meteo](https://open-meteo.com/). Không cần API key thời tiết.

## Lệnh

| Lệnh | Việc làm |
| --- | --- |
| `/start` | Hướng dẫn và nút gửi vị trí |
| `/city Hà Nội` | Đặt vị trí theo tên |
| `/weather` | Bản tin ngắn |
| `/forecast` | Thêm giờ mọc/lặn và UV |
| `/on` `/off` | Bật hoặc tắt nhắc 3 giờ |
| `/quiet 22 6` | Không nhắc từ 22h đến 6h |
| `/quiet off` | Bỏ giờ im lặng |
| `/status` | Vị trí và trạng thái |

Gửi vị trí GPS thì bot đổi thành tên phường/thành phố. `/weather` vẫn dùng được trong giờ im lặng.

## Chạy bot tương tác

Cần Python 3.11+ và máy luôn bật nếu muốn lịch 3 giờ của `bot.py`.

```bash
cd telegram-weather-bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Điền `BOT_TOKEN` từ [@BotFather](https://t.me/BotFather) (`/newbot`), rồi `python bot.py`.

## Deploy miễn phí: GitHub Actions

Repo public: runner chuẩn miễn phí. Repo private: khoảng 8 lần/ngày, dưới hạn mức 2.000 phút/tháng. Không cần `pip install` — `notify.py` chỉ dùng thư viện Python sẵn có.

1. Đẩy thư mục này lên GitHub. Không đẩy `.env` hay `subscribers.json` (đã có trong `.gitignore`).
2. Settings → Secrets and variables → Actions:
   - `BOT_TOKEN`
   - `CHAT_ID` — nhắn `/start` cho bot, mở `https://api.telegram.org/bot<TOKEN>/getUpdates`, lấy `message.chat.id`
   - `LAT` / `LON` — ví dụ Hải Phòng `20.8449` và `106.6881`
   - `PLACE` — tên hiển thị, tuỳ chọn
   - `QUIET_FROM` / `QUIET_TO` — tuỳ chọn, ví dụ `22` và `6`
3. Tab Actions → `weather-every-3h` → Run workflow.

Lịch `7 */3 * * *` UTC là 7h, 10h, 13h, 16h, 19h, 22h, 1h, 4h giờ Việt Nam. GitHub có thể trễ vài phút. Nếu đang trong giờ im lặng, lần chạy đó bỏ qua, không báo lỗi.

Nhiều người nhận: secret `SUBSCRIBERS_JSON`, dạng giống `subscribers.json` (`users` → mỗi người có `chat_id`, `lat`, `lon`, `place`, và tuỳ chọn `quiet_from`, `quiet_to`, `timezone`).
