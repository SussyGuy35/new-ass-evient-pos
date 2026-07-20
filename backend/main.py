"""
EViENT POS - FastAPI Application Entry Point

Wires up:
    * Lifespan events (DB connect / seed / disconnect)
    * CORS middleware (allow all origins for dev)
    * API routers under ``/api``
    * Optional static-file serving of the frontend directory
    * Root redirect to ``/index.html``
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from config import settings
from database import close_db, connect_db
from routes.auth_routes import router as auth_router
from routes.drawer_routes import router as drawer_router
from routes.hardware_routes import router as hardware_router
from routes.invoice_routes import router as invoice_router
from routes.log_routes import router as log_router
from routes.order_routes import router as order_router
from routes.product_routes import router as product_router
from routes.report_routes import router as report_router
from seed import seed_admin


# --------------------------------------------------------------------------
# Lifespan
# --------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: connect to DB and seed on startup, close on shutdown."""
    import local_db
    import sync_engine

    # 1. Connect MongoDB
    await connect_db()
    await seed_admin()

    # 2. Init local SQLite cache
    await local_db.init_db()

    # 3. Initial sync: pull products/users from MongoDB into SQLite
    online = await sync_engine.check_online()
    if online:
        await sync_engine.sync_remote_to_local()

    # 4. Start background sync loop
    sync_task = asyncio.create_task(sync_engine.start_sync_loop())

    yield

    # Shutdown
    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass
    await local_db.close_db()
    await close_db()


# --------------------------------------------------------------------------
# App instance
# --------------------------------------------------------------------------

app = FastAPI(
    title="EViENT POS API",
    description="Point-of-Sale backend for the EViENT POS system.",
    version="1.0.0",
    lifespan=lifespan,
)

# --------------------------------------------------------------------------
# CORS
# --------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000", "http://localhost", "http://127.0.0.1"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------
# API routers
# --------------------------------------------------------------------------

app.include_router(auth_router, prefix="/api")
app.include_router(product_router, prefix="/api")
app.include_router(drawer_router, prefix="/api")
app.include_router(order_router, prefix="/api")
app.include_router(invoice_router, prefix="/api")
app.include_router(log_router, prefix="/api")
app.include_router(hardware_router, prefix="/api")
app.include_router(report_router, prefix="/api")


# --------------------------------------------------------------------------
# Root redirect
# --------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def root():
    """Redirect the root URL to the frontend ``index.html``."""
    return RedirectResponse(url="/index.html")


@app.get("/config.js", include_in_schema=False)
async def get_frontend_config():
    """Serve the frontend config dynamically based on environment variables."""
    # Convert unicode string back to literal escape sequences for JS safely
    cash_drawer = settings.CASH_DRAWER_COMMAND.encode('unicode_escape').decode('utf-8')
    js_content = f"""/**
 * EViENT POS - Application Configuration (Auto-generated)
 */
const APP_CONFIG = {{
    API_BASE_URL: {json.dumps(settings.API_BASE_URL)},
    CASH_DRAWER_COMMAND: {json.dumps(cash_drawer)},
    BAUD_RATE: {json.dumps(settings.BAUD_RATE)},
    BARCODE_TIMEOUT: {json.dumps(settings.BARCODE_TIMEOUT)},
    ITEMS_PER_PAGE: {json.dumps(settings.ITEMS_PER_PAGE)},
    VIETQR_BANK_ID: {json.dumps(settings.VIETQR_BANK_ID)},
    VIETQR_ACCOUNT_NO: {json.dumps(settings.VIETQR_ACCOUNT_NO)},
    VIETQR_ACCOUNT_NAME: {json.dumps(settings.VIETQR_ACCOUNT_NAME)},
    VAT_RATE: {json.dumps(settings.VAT_RATE)}
}};
"""
    return Response(content=js_content, media_type="application/javascript")


# --------------------------------------------------------------------------
# Static files (frontend)
# --------------------------------------------------------------------------

_frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(_frontend_dir):
    app.mount(
        "/",
        StaticFiles(directory=_frontend_dir, html=True),
        name="frontend",
    )
    print(f"[APP] Serving frontend from: {os.path.abspath(_frontend_dir)}")
else:
    print("[APP] Frontend directory not found – skipping static mount.")
