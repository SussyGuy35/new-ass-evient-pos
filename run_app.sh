#!/bin/bash
# Script khởi động cả Backend và Client (Frontend) cho EViENT POS

# Xác định thư mục hiện tại của script
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"

# 1. Khởi động Backend ở chế độ chạy ngầm
echo "Đang khởi động Backend Server..."
bash "$APP_DIR/start.sh" &
SERVER_PID=$!

# Đợi khoảng 3 giây để server Uvicorn kịp mở cổng 8000
sleep 3

# 2. Khởi động Client (Google Chrome Kiosk Mode)
# Sử dụng --user-data-dir riêng để đảm bảo tiến trình Chrome không bị gộp vào session đang mở của người dùng (gây tắt script ngay lập tức)
echo "Đang khởi động Client POS..."
CHROME_PROFILE="$APP_DIR/chrome_profile"
google-chrome --user-data-dir="$CHROME_PROFILE" --kiosk --disable-dev-shm-usage --disable-extensions --disable-background-networking --disable-sync --disable-translate --no-first-run --disable-infobars --autoplay-policy=no-user-gesture-required http://localhost:8000/login.html

# 3. Tự động dọn dẹp: Khi bạn nhấn Alt+F4 hoặc đóng Chrome, script sẽ chạy tiếp xuống đây và tắt Backend
echo "Đang tắt Backend Server..."
kill $SERVER_PID
