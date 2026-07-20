"""
EViENT POS - Local SQLite Database (Offline Cache & Buffer)

Provides an async SQLite layer that mirrors critical MongoDB data locally
and buffers write operations when the remote database is unreachable.

Tables:
    products            – cached product catalog (read fallback)
    users               – cached user credentials (login fallback)
    pending_orders      – orders created while offline (awaiting sync)
    pending_drawer_txs  – drawer transactions created offline
    pending_logs        – audit logs created offline
    drawer_state        – local drawer balance tracker
    sync_meta           – metadata about sync status
"""

import json
import os
from datetime import datetime, timezone

import aiosqlite

# Path to the SQLite database file
_DB_DIR = os.path.join(os.path.dirname(__file__), "data")
_DB_PATH = os.path.join(_DB_DIR, "local_cache.db")

_conn: aiosqlite.Connection | None = None


# --------------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------------

async def init_db() -> None:
    """Initialise the SQLite database: create file + tables if needed."""
    global _conn
    os.makedirs(_DB_DIR, exist_ok=True)
    _conn = await aiosqlite.connect(_DB_PATH)
    _conn.row_factory = aiosqlite.Row
    await _conn.execute("PRAGMA journal_mode=WAL")  # better concurrency
    await _create_tables()
    print(f"[LOCAL_DB] SQLite initialised at {_DB_PATH}")


async def close_db() -> None:
    """Close the SQLite connection."""
    global _conn
    if _conn:
        await _conn.close()
        _conn = None
        print("[LOCAL_DB] SQLite connection closed.")


async def _create_tables() -> None:
    """Create all required tables if they don't already exist."""
    await _conn.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            barcode TEXT,
            price REAL NOT NULL,
            category TEXT,
            stock INTEGER DEFAULT 0,
            image_url TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT,
            role TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS pending_orders (
            local_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_data TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pending_drawer_txs (
            local_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_data TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pending_logs (
            local_id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_data TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS drawer_state (
            id TEXT PRIMARY KEY DEFAULT 'main',
            balance REAL DEFAULT 0,
            last_updated TEXT
        );

        CREATE TABLE IF NOT EXISTS sync_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS offline_counter (
            date_key TEXT PRIMARY KEY,
            seq INTEGER DEFAULT 0
        );
    """)
    # Ensure drawer_state has a row
    await _conn.execute(
        "INSERT OR IGNORE INTO drawer_state (id, balance, last_updated) VALUES ('main', 0, ?)",
        (datetime.now(timezone.utc).isoformat(),)
    )
    await _conn.commit()


# --------------------------------------------------------------------------
# Product cache
# --------------------------------------------------------------------------

async def cache_products(products: list[dict]) -> None:
    """Replace the local product cache with fresh data from MongoDB."""
    await _conn.execute("DELETE FROM products")
    for p in products:
        await _conn.execute(
            """INSERT OR REPLACE INTO products (id, name, barcode, price, category, stock, image_url, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(p.get("_id", p.get("id", ""))),
                p.get("name", ""),
                p.get("barcode"),
                p.get("price", 0),
                p.get("category"),
                p.get("stock", 0),
                p.get("image_url"),
                p.get("created_at", "").isoformat() if hasattr(p.get("created_at", ""), "isoformat") else str(p.get("created_at", "")),
            )
        )
    await _conn.commit()
    print(f"[LOCAL_DB] Cached {len(products)} products.")


async def get_cached_products(page: int = 1, per_page: int = 20, q: str | None = None) -> tuple[list[dict], int]:
    """Read products from the local cache with pagination and optional search."""
    where = ""
    params: list = []
    if q:
        where = "WHERE name LIKE ? OR barcode LIKE ?"
        params = [f"%{q}%", f"%{q}%"]

    # Total count
    row = await _conn.execute_fetchall(f"SELECT COUNT(*) as cnt FROM products {where}", params)
    total = row[0][0] if row else 0

    # Paginated results
    offset = (page - 1) * per_page
    rows = await _conn.execute_fetchall(
        f"SELECT * FROM products {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [per_page, offset]
    )

    items = []
    for r in rows:
        items.append({
            "id": r[0], "name": r[1], "barcode": r[2], "price": r[3],
            "category": r[4], "stock": r[5], "image_url": r[6], "created_at": r[7],
        })
    return items, total


async def get_cached_product_by_barcode(barcode: str) -> dict | None:
    """Find a cached product by exact barcode."""
    rows = await _conn.execute_fetchall(
        "SELECT * FROM products WHERE barcode = ?", (barcode,)
    )
    if not rows:
        return None
    r = rows[0]
    return {
        "id": r[0], "name": r[1], "barcode": r[2], "price": r[3],
        "category": r[4], "stock": r[5], "image_url": r[6], "created_at": r[7],
    }


async def deduct_cached_stock(product_id: str, qty: int) -> None:
    """Deduct stock from the local product cache."""
    await _conn.execute(
        "UPDATE products SET stock = MAX(0, stock - ?) WHERE id = ?",
        (qty, product_id)
    )
    await _conn.commit()


# --------------------------------------------------------------------------
# User cache
# --------------------------------------------------------------------------

async def cache_users(users: list[dict]) -> None:
    """Replace the local user cache with fresh data from MongoDB."""
    await _conn.execute("DELETE FROM users")
    for u in users:
        await _conn.execute(
            """INSERT OR REPLACE INTO users (id, username, password, full_name, role, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(u.get("_id", u.get("id", ""))),
                u.get("username", ""),
                u.get("password", ""),
                u.get("full_name", ""),
                u.get("role", "employee"),
                u.get("created_at", "").isoformat() if hasattr(u.get("created_at", ""), "isoformat") else str(u.get("created_at", "")),
            )
        )
    await _conn.commit()
    print(f"[LOCAL_DB] Cached {len(users)} users.")


async def get_cached_user_by_id(user_id: str) -> dict | None:
    """Find a cached user by ID."""
    rows = await _conn.execute_fetchall(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    )
    if not rows:
        return None
    r = rows[0]
    return {
        "_id": r[0], "id": r[0], "username": r[1], "password": r[2],
        "full_name": r[3], "role": r[4], "created_at": r[5],
    }


async def get_cached_user_by_username(username: str) -> dict | None:
    """Find a cached user by username."""
    rows = await _conn.execute_fetchall(
        "SELECT * FROM users WHERE username = ?", (username,)
    )
    if not rows:
        return None
    r = rows[0]
    return {
        "_id": r[0], "id": r[0], "username": r[1], "password": r[2],
        "full_name": r[3], "role": r[4], "created_at": r[5],
    }


# --------------------------------------------------------------------------
# Pending orders (offline buffer)
# --------------------------------------------------------------------------

async def queue_order(order_doc: dict) -> None:
    """Store an order in the pending queue for later sync to MongoDB."""
    await _conn.execute(
        "INSERT INTO pending_orders (order_data, created_at) VALUES (?, ?)",
        (json.dumps(order_doc, default=str), datetime.now(timezone.utc).isoformat())
    )
    await _conn.commit()


async def pop_pending_orders() -> list[dict]:
    """Retrieve and delete all pending orders (for sync)."""
    rows = await _conn.execute_fetchall(
        "SELECT local_id, order_data FROM pending_orders ORDER BY local_id ASC"
    )
    items = []
    for r in rows:
        items.append({"local_id": r[0], "data": json.loads(r[1])})
    return items


async def get_pending_order_by_id(order_id: str) -> dict | None:
    """Find a specific pending order by its MongoDB _id string."""
    rows = await _conn.execute_fetchall(
        "SELECT order_data FROM pending_orders WHERE order_data LIKE ?",
        (f'%"{order_id}"%',)
    )
    for r in rows:
        data = json.loads(r[0])
        if str(data.get("_id")) == order_id:
            return data
    return None


async def remove_pending_order(local_id: int) -> None:
    """Remove a specific pending order after successful sync."""
    await _conn.execute("DELETE FROM pending_orders WHERE local_id = ?", (local_id,))
    await _conn.commit()


# --------------------------------------------------------------------------
# Pending drawer transactions (offline buffer)
# --------------------------------------------------------------------------

async def queue_drawer_tx(tx_doc: dict) -> None:
    """Store a drawer transaction in the pending queue."""
    await _conn.execute(
        "INSERT INTO pending_drawer_txs (tx_data, created_at) VALUES (?, ?)",
        (json.dumps(tx_doc, default=str), datetime.now(timezone.utc).isoformat())
    )
    await _conn.commit()


async def pop_pending_drawer_txs() -> list[dict]:
    """Retrieve all pending drawer transactions."""
    rows = await _conn.execute_fetchall(
        "SELECT local_id, tx_data FROM pending_drawer_txs ORDER BY local_id ASC"
    )
    return [{"local_id": r[0], "data": json.loads(r[1])} for r in rows]


async def remove_pending_drawer_tx(local_id: int) -> None:
    """Remove a specific pending drawer tx after successful sync."""
    await _conn.execute("DELETE FROM pending_drawer_txs WHERE local_id = ?", (local_id,))
    await _conn.commit()


# --------------------------------------------------------------------------
# Pending audit logs (offline buffer)
# --------------------------------------------------------------------------

async def queue_log(log_doc: dict) -> None:
    """Store an audit log entry in the pending queue."""
    await _conn.execute(
        "INSERT INTO pending_logs (log_data, created_at) VALUES (?, ?)",
        (json.dumps(log_doc, default=str), datetime.now(timezone.utc).isoformat())
    )
    await _conn.commit()


async def pop_pending_logs() -> list[dict]:
    """Retrieve all pending audit logs."""
    rows = await _conn.execute_fetchall(
        "SELECT local_id, log_data FROM pending_logs ORDER BY local_id ASC"
    )
    return [{"local_id": r[0], "data": json.loads(r[1])} for r in rows]


async def remove_pending_log(local_id: int) -> None:
    """Remove a specific pending log after successful sync."""
    await _conn.execute("DELETE FROM pending_logs WHERE local_id = ?", (local_id,))
    await _conn.commit()


# --------------------------------------------------------------------------
# Local drawer state
# --------------------------------------------------------------------------

async def get_local_drawer_balance() -> float:
    """Get the current local drawer balance."""
    rows = await _conn.execute_fetchall(
        "SELECT balance FROM drawer_state WHERE id = 'main'"
    )
    return rows[0][0] if rows else 0.0


async def update_local_drawer_balance(amount: float) -> float:
    """Increment the local drawer balance and return new value."""
    now = datetime.now(timezone.utc).isoformat()
    await _conn.execute(
        "UPDATE drawer_state SET balance = balance + ?, last_updated = ? WHERE id = 'main'",
        (amount, now)
    )
    await _conn.commit()
    return await get_local_drawer_balance()


async def set_local_drawer_balance(balance: float) -> None:
    """Set the local drawer balance to an exact value (used during sync)."""
    now = datetime.now(timezone.utc).isoformat()
    await _conn.execute(
        "UPDATE drawer_state SET balance = ?, last_updated = ? WHERE id = 'main'",
        (balance, now)
    )
    await _conn.commit()


# --------------------------------------------------------------------------
# Offline order number counter
# --------------------------------------------------------------------------

async def next_offline_order_number() -> str:
    """Generate the next offline order number for today."""
    today = datetime.now().strftime("%Y%m%d")
    await _conn.execute(
        "INSERT OR IGNORE INTO offline_counter (date_key, seq) VALUES (?, 0)",
        (today,)
    )
    await _conn.execute(
        "UPDATE offline_counter SET seq = seq + 1 WHERE date_key = ?",
        (today,)
    )
    await _conn.commit()
    rows = await _conn.execute_fetchall(
        "SELECT seq FROM offline_counter WHERE date_key = ?", (today,)
    )
    seq = rows[0][0] if rows else 1
    return f"OFFLINE-{today}-{seq:04d}"


# --------------------------------------------------------------------------
# Sync metadata
# --------------------------------------------------------------------------

async def get_meta(key: str) -> str | None:
    """Get a sync metadata value."""
    rows = await _conn.execute_fetchall(
        "SELECT value FROM sync_meta WHERE key = ?", (key,)
    )
    return rows[0][0] if rows else None


async def set_meta(key: str, value: str) -> None:
    """Set a sync metadata value."""
    await _conn.execute(
        "INSERT OR REPLACE INTO sync_meta (key, value) VALUES (?, ?)",
        (key, value)
    )
    await _conn.commit()


async def get_pending_counts() -> dict:
    """Get counts of all pending items awaiting sync."""
    orders = await _conn.execute_fetchall("SELECT COUNT(*) FROM pending_orders")
    drawer = await _conn.execute_fetchall("SELECT COUNT(*) FROM pending_drawer_txs")
    logs = await _conn.execute_fetchall("SELECT COUNT(*) FROM pending_logs")
    return {
        "orders": orders[0][0] if orders else 0,
        "drawer_txs": drawer[0][0] if drawer else 0,
        "logs": logs[0][0] if logs else 0,
    }
