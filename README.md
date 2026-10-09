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

Vị trí không ghim trong secret. Bạn gửi vị trí trên Telegram, workflow ghi vào `subscribers.json` và lần chạy sau dùng đúng chỗ đó. Đổi chỗ thì gửi vị trí mới hoặc `/city`.

Chỉ cần một secret: `BOT_TOKEN`. Không cần `CHAT_ID`, `LAT`, `LON`.

Repo nên để private. File `subscribers.json` chứa tọa độ bạn gửi. Repo public thì ai cũng xem được.

1. Đẩy cả thư mục này lên GitHub, kể cả `subscribers.json` và `.github/workflows/weather.yml`.
2. Settings → Secrets and variables → Actions → New repository secret: tên `BOT_TOKEN`, giá trị là token BotFather.
3. Tab Actions → `weather-every-3h` → Run workflow một lần, để GitHub bật lịch.
4. Mở bot, gõ `/start`, bấm gửi vị trí hoặc gõ `/city Hải Phòng`.
5. Chạy lại workflow ngay. Bot trả lời và nhớ vị trí. Những lần sau (khoảng 7h, 10h, 13h, 16h, 19h, 22h, 1h, 4h giờ Việt Nam) tự gửi, không cần sửa tọa độ.

GitHub có thể trễ vài phút. Lệnh bạn gõ chỉ được xử lý khi workflow chạy, nên sau khi đổi vị trí hãy bấm Run workflow nếu chưa đến giờ nhắc.

Không chạy `bot.py` cùng lúc với Action. Hai bên cùng nghe Telegram sẽ tranh nhau.
