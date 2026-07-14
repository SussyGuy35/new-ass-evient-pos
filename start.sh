#!/bin/bash
# Script khởi động EViENT POS cho Linux/macOS

cd "$(dirname "$0")/backend"

# Cài đặt môi trường ảo nếu chưa có
if [ ! -d "venv" ]; then
    echo "Đang tạo virtual environment..."
    python3 -m venv venv
fi

# Kích hoạt môi trường ảo
source venv/bin/activate

# Cài đặt dependencies nếu có thay đổi (chạy tự động)
echo "Kiểm tra dependencies..."
PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 pip install -r requirements.txt

# Khởi động ứng dụng
echo "Khởi động EViENT POS Backend..."
uvicorn main:app --host 0.0.0.0 --port 8000
