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
            stock_reserved INTEGER DEFAULT 0,
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

        CREATE TABLE IF NOT EXISTS preorders (
            id TEXT PRIMARY KEY,
            barcode_code TEXT UNIQUE NOT NULL,
            customer_name TEXT NOT NULL,
            email TEXT,
            items TEXT,
            subtotal REAL,
            vat_rate REAL,
            vat_amount REAL,
            total REAL,
            status TEXT DEFAULT 'pending',
            note TEXT DEFAULT '',
            created_by TEXT,
            created_at TEXT,
            fulfilled_at TEXT,
            fulfilled_by TEXT,
            order_id TEXT
        );

        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            order_data TEXT NOT NULL,
            order_number TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS pending_preorder_fulfills (
            local_id INTEGER PRIMARY KEY AUTOINCREMENT,
            fulfill_data TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)

    # Migration: add stock_reserved and preorder_price to products table if they don't exist
    try:
        await _conn.execute("ALTER TABLE products ADD COLUMN stock_reserved INTEGER DEFAULT 0")
    except aiosqlite.OperationalError:
        pass
    try:
        await _conn.execute("ALTER TABLE products ADD COLUMN preorder_price REAL")
    except aiosqlite.OperationalError:
        pass

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
    await _conn.executemany(
        """
        INSERT INTO products (id, name, barcode, price, preorder_price, category, stock, stock_reserved, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name,
            barcode=excluded.barcode,
            price=excluded.price,
            preorder_price=excluded.preorder_price,
            category=excluded.category,
            stock=excluded.stock,
            stock_reserved=excluded.stock_reserved
        """,
        [(
            str(p.get("_id", p.get("id", ""))), p["name"], p.get("barcode"), p["price"], p.get("preorder_price"),
            p.get("category"), p.get("stock", 0), p.get("stock_reserved", 0),
            str(p.get("created_at", ""))
        ) for p in products]
    )
    await _conn.commit()
    print(f"[LOCAL_DB] Cached {len(products)} products.")


async def get_cached_products(page: int = 1, per_page: int = 20, q: str | None = None, sort_by: str = "created_at", order: str = "desc") -> tuple[list[dict], int]:
    """Read products from the local cache with pagination, optional search, and sorting."""
    where = ""
    params: list = []
    if q:
        where = "WHERE name LIKE ? OR barcode LIKE ?"
        params = [f"%{q}%", f"%{q}%"]

    # Total count
    row = await _conn.execute_fetchall(f"SELECT COUNT(*) as cnt FROM products {where}", params)
    total = row[0][0] if row else 0

    valid_sort_fields = {"created_at", "name", "price", "stock"}
    sort_field = sort_by if sort_by in valid_sort_fields else "created_at"
    sort_dir = "ASC" if order.lower() == "asc" else "DESC"

    # Paginated results
    offset = (page - 1) * per_page
    rows = await _conn.execute_fetchall(
        f"SELECT * FROM products {where} ORDER BY {sort_field} {sort_dir} LIMIT ? OFFSET ?",
        params + [per_page, offset]
    )

    items = []
    for r in rows:
        items.append({
            "id": r["id"], 
            "name": r["name"], 
            "barcode": r["barcode"], 
            "price": r["price"], 
            "preorder_price": r["preorder_price"] if "preorder_price" in r.keys() else None,
            "category": r["category"], 
            "stock": r["stock"], 
            "stock_reserved": r["stock_reserved"] if "stock_reserved" in r.keys() else 0, 
            "created_at": r["created_at"],
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
        "id": r["id"], 
        "name": r["name"], 
        "barcode": r["barcode"], 
        "price": r["price"], 
        "preorder_price": r["preorder_price"] if "preorder_price" in r.keys() else None,
        "category": r["category"], 
        "stock": r["stock"], 
        "stock_reserved": r["stock_reserved"] if "stock_reserved" in r.keys() else 0, 
        "created_at": r["created_at"],
    }


async def deduct_cached_stock(product_id: str, qty: int, reserve_qty: int = 0) -> None:
    """Deduct stock from the local product cache."""
    await _conn.execute(
        "UPDATE products SET stock = MAX(0, stock - ?), stock_reserved = MAX(0, stock_reserved - ?) WHERE id = ?",
        (qty, reserve_qty, product_id)
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
    fulfills = await _conn.execute_fetchall("SELECT COUNT(*) FROM pending_preorder_fulfills")
    return {
        "orders": orders[0][0] if orders else 0,
        "drawer_txs": drawer[0][0] if drawer else 0,
        "logs": logs[0][0] if logs else 0,
        "preorder_fulfills": fulfills[0][0] if fulfills else 0,
    }


# --------------------------------------------------------------------------
# Pre-order cache
# --------------------------------------------------------------------------

async def cache_preorders(preorders: list[dict]) -> None:
    """Replace the local preorder cache with fresh data from MongoDB."""
    await _conn.execute("DELETE FROM preorders")
    for p in preorders:
        await _conn.execute(
            """INSERT OR REPLACE INTO preorders
               (id, barcode_code, customer_name, email, items, subtotal,
                vat_rate, vat_amount, total, status, note, created_by,
                created_at, fulfilled_at, fulfilled_by, order_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(p.get("_id", p.get("id", ""))),
                p.get("barcode_code", ""),
                p.get("customer_name", ""),
                p.get("email", ""),
                json.dumps(p.get("items", []), default=str),
                p.get("subtotal", 0),
                p.get("vat_rate", 0),
                p.get("vat_amount", 0),
                p.get("total", 0),
                p.get("status", "pending"),
                p.get("note", ""),
                p.get("created_by", ""),
                str(p.get("created_at", "")),
                str(p.get("fulfilled_at", "")) if p.get("fulfilled_at") else None,
                p.get("fulfilled_by"),
                p.get("order_id"),
            )
        )
    await _conn.commit()
    print(f"[LOCAL_DB] Cached {len(preorders)} preorders.")


def _row_to_preorder(r) -> dict:
    """Convert a preorders table row to a dict matching PreOrderResponse."""
    return {
        "id": r[0],
        "_id": r[0],
        "barcode_code": r[1],
        "customer_name": r[2],
        "email": r[3],
        "items": json.loads(r[4]) if r[4] else [],
        "subtotal": r[5] or 0,
        "vat_rate": r[6] or 0,
        "vat_amount": r[7] or 0,
        "total": r[8] or 0,
        "status": r[9] or "pending",
        "note": r[10] or "",
        "created_by": r[11] or "",
        "created_at": r[12] or "",
        "fulfilled_at": r[13],
        "fulfilled_by": r[14],
        "order_id": r[15],
    }


async def get_cached_preorders(
    page: int = 1, per_page: int = 20, status_filter: str | None = None
) -> tuple[list[dict], int]:
    """Read preorders from the local cache with pagination and optional status filter."""
    where = ""
    params: list = []
    if status_filter:
        where = "WHERE status = ?"
        params = [status_filter]

    row = await _conn.execute_fetchall(
        f"SELECT COUNT(*) FROM preorders {where}", params
    )
    total = row[0][0] if row else 0

    offset = (page - 1) * per_page
    rows = await _conn.execute_fetchall(
        f"SELECT * FROM preorders {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [per_page, offset],
    )
    items = [_row_to_preorder(r) for r in rows]
    return items, total


async def get_cached_preorder_by_barcode(barcode_code: str) -> dict | None:
    """Find a cached preorder by barcode_code."""
    rows = await _conn.execute_fetchall(
        "SELECT * FROM preorders WHERE barcode_code = ?", (barcode_code,)
    )
    if not rows:
        return None
    return _row_to_preorder(rows[0])


async def get_cached_preorder_by_id(preorder_id: str) -> dict | None:
    """Find a cached preorder by ID."""
    rows = await _conn.execute_fetchall(
        "SELECT * FROM preorders WHERE id = ?", (preorder_id,)
    )
    if not rows:
        return None
    return _row_to_preorder(rows[0])


async def update_cached_preorder_status(
    preorder_id: str,
    new_status: str,
    fulfilled_at: str | None = None,
    fulfilled_by: str | None = None,
    order_id: str | None = None,
) -> None:
    """Update a cached preorder's status (e.g. after offline fulfill)."""
    await _conn.execute(
        """UPDATE preorders
           SET status = ?, fulfilled_at = ?, fulfilled_by = ?, order_id = ?
           WHERE id = ?""",
        (new_status, fulfilled_at, fulfilled_by, order_id, preorder_id),
    )
    await _conn.commit()


# --------------------------------------------------------------------------
# Order cache (recent orders for offline read)
# --------------------------------------------------------------------------

async def cache_orders(orders: list[dict]) -> None:
    """Replace the local order cache with recent data from MongoDB."""
    await _conn.execute("DELETE FROM orders")
    for o in orders:
        doc = dict(o)
        oid = str(doc.pop("_id", doc.get("id", "")))
        await _conn.execute(
            "INSERT OR REPLACE INTO orders (id, order_data, order_number, created_at) VALUES (?, ?, ?, ?)",
            (
                oid,
                json.dumps(doc, default=str),
                doc.get("order_number", ""),
                str(doc.get("created_at", "")),
            ),
        )
    await _conn.commit()
    print(f"[LOCAL_DB] Cached {len(orders)} orders.")


async def get_cached_orders(
    page: int = 1, per_page: int = 20, date: str | None = None
) -> tuple[list[dict], int]:
    """Read orders from the local cache with pagination and optional date filter."""
    where = ""
    params: list = []
    if date:
        where = "WHERE created_at LIKE ?"
        params = [f"{date}%"]

    row = await _conn.execute_fetchall(
        f"SELECT COUNT(*) FROM orders {where}", params
    )
    total = row[0][0] if row else 0

    offset = (page - 1) * per_page
    rows = await _conn.execute_fetchall(
        f"SELECT id, order_data FROM orders {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [per_page, offset],
    )
    items = []
    for r in rows:
        doc = json.loads(r[1])
        doc["id"] = r[0]
        items.append(doc)
    return items, total


async def get_cached_order_by_id(order_id: str) -> dict | None:
    """Find a cached order by ID."""
    rows = await _conn.execute_fetchall(
        "SELECT id, order_data FROM orders WHERE id = ?", (order_id,)
    )
    if not rows:
        return None
    doc = json.loads(rows[0][1])
    doc["id"] = rows[0][0]
    return doc


async def save_single_order(order_doc: dict) -> None:
    """Save a single order to the local cache (used after online/offline creation)."""
    doc = dict(order_doc)
    oid = str(doc.pop("_id", doc.get("id", "")))
    await _conn.execute(
        "INSERT OR REPLACE INTO orders (id, order_data, order_number, created_at) VALUES (?, ?, ?, ?)",
        (
            oid,
            json.dumps(doc, default=str),
            doc.get("order_number", ""),
            str(doc.get("created_at", "")),
        ),
    )
    await _conn.commit()


# --------------------------------------------------------------------------
# Pending preorder fulfills (offline buffer)
# --------------------------------------------------------------------------

async def queue_preorder_fulfill(data: dict) -> None:
    """Store a preorder fulfill action in the pending queue."""
    await _conn.execute(
        "INSERT INTO pending_preorder_fulfills (fulfill_data, created_at) VALUES (?, ?)",
        (json.dumps(data, default=str), datetime.now(timezone.utc).isoformat()),
    )
    await _conn.commit()


async def pop_pending_preorder_fulfills() -> list[dict]:
    """Retrieve all pending preorder fulfills."""
    rows = await _conn.execute_fetchall(
        "SELECT local_id, fulfill_data FROM pending_preorder_fulfills ORDER BY local_id ASC"
    )
    return [{"local_id": r[0], "data": json.loads(r[1])} for r in rows]


async def remove_pending_preorder_fulfill(local_id: int) -> None:
    """Remove a specific pending preorder fulfill after successful sync."""
    await _conn.execute(
        "DELETE FROM pending_preorder_fulfills WHERE local_id = ?", (local_id,)
    )
    await _conn.commit()
