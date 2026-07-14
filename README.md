# EViENT POS

EViENT POS is a modern, lightweight Point-of-Sale (POS) application tailored for low-end hardware, optimized for touch screens, and fully integrated with hardware such as barcode scanners and cash drawers.

## Features

- **Lightweight Architecture**: Static HTML/JS frontend powered by a FastAPI Python backend. No heavy Node.js or React frameworks.
- **Hardware Integration**:
  - Direct Cash Drawer communication via the Web Serial API straight from the browser.
  - Native HID Barcode Scanner support with smart event buffering.
- **Performance Optimized**: DOM manipulations are heavily isolated. Virtual scrolling and pagination prevent browser lag on weaker devices (like embedded Debian GNOME setups).
- **Asynchronous Backend**: Powered by FastAPI and the Motor async driver for MongoDB.
- **Invoice Generation**: Dynamically creates PNG invoices using the Python `Pillow` library rather than direct thermal printing.
- **Security**: Built-in Role-Based Access Control (RBAC) with Admin, Manager, and Employee levels, complete with audit logging for all critical actions.

## Directory Structure

- `backend/`: FastAPI Python application.
- `frontend/`: Static HTML5, Vanilla JS, and Tailwind CSS files.
- `.env`: Unified configuration file for both backend and frontend.
- `start.sh` / `start.bat`: Quick-start runner scripts.

## Prerequisites

1. **Python 3.10+** (Tested on Python 3.14.6)
2. **MongoDB Server** (Must be running before starting the app)
3. **Chrome / Chromium Browser** (Required for Web Serial API support)

## Configuration

All application configurations are managed centrally in the `.env` file located in the root directory.

```dotenv
# --- BACKEND SETTINGS ---
MONGO_URI=mongodb://localhost:27017
DB_NAME=evient_pos
JWT_SECRET=evient-pos-secret-key-2024
JWT_EXPIRATION=28800

# --- FRONTEND SETTINGS ---
API_BASE_URL=http://localhost:8000/api
CASH_DRAWER_COMMAND=\x1B\x70\x00\x19\xFA
BAUD_RATE=9600
BARCODE_TIMEOUT=100
ITEMS_PER_PAGE=20
```

> Note: The FastAPI backend automatically serves these frontend variables dynamically via the `/config.js` endpoint, eliminating the need to maintain separate config files.

## Running the Application

### Method 1: Using the Quick-Start Script (Recommended)

**Linux / macOS**
```bash
# Make the script executable (only needed once)
chmod +x start.sh

# Run the script
./start.sh
```

**Windows**
```cmd
start.bat
```
*These scripts will automatically create a virtual environment, install the required dependencies, and launch the Uvicorn server.*

### Method 2: Manual Startup

1. Open a terminal and navigate to the `backend/` directory.
2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 pip install -r requirements.txt
   ```
4. Run the backend server:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

### Accessing the POS

Once the server is running, open a Chrome-based browser and navigate to:
**http://localhost:8000/login.html**

**Default Admin Credentials:**
- **Username**: `evientadmin`
- **Password**: `@dmin123`
*(This account is automatically seeded into the database on the first successful run).*

## Deployment

For production deployment on Linux (Debian/GNOME setups), the repository includes:
- `evient_pos.service`: A Systemd service file to run the FastAPI backend as a daemon.
- `evient_client.desktop`: A GNOME autostart entry to launch the Chrome browser in Kiosk mode upon login.
