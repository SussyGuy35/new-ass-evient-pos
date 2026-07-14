@echo off
REM Script khởi động EViENT POS cho Windows
chcp 65001 >nul

cd "%~dp0backend"

REM Cài đặt môi trường ảo nếu chưa có
IF NOT EXIST "venv\" (
    echo Đang tạo virtual environment...
    python -m venv venv
)

REM Kích hoạt môi trường ảo
call venv\Scripts\activate.bat

REM Cài đặt dependencies nếu có thay đổi
echo Kiểm tra dependencies...
set PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1
pip install -r requirements.txt

REM Khởi động ứng dụng
echo Khởi động EViENT POS Backend...
uvicorn main:app --host 0.0.0.0 --port 8000
pause
