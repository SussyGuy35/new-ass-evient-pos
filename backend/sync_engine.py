"""
EViENT POS - Sync Engine

Background task that periodically:
    1. Checks MongoDB connectivity (ping).
    2. Pushes buffered offline data (orders, drawer txs, logs) to MongoDB.
    3. Pulls fresh product/user data from MongoDB into the local SQLite cache.
"""

import asyncio
import traceback
from datetime import datetime, timezone

from pymongo.errors import (
    ConnectionFailure,
    ServerSelectionTimeoutError,
    NetworkTimeout,
    AutoReconnect,
)

import local_db
from database import get_collection, client as _mongo_client

# --------------------------------------------------------------------------
# Global online state
# --------------------------------------------------------------------------

_is_online: bool = True
SYNC_INTERVAL_SECONDS = 60
PING_TIMEOUT_MS = 3000

# MongoDB errors that indicate connectivity problems
MONGO_NETWORK_ERRORS = (
    ConnectionFailure,
    ServerSelectionTimeoutError,
    NetworkTimeout,
    AutoReconnect,
    OSError,
    TimeoutError,
)


def is_online() -> bool:
    """Return current connectivity status."""
    return _is_online

def set_offline() -> None:
    """Instantly mark the system as offline from a route failure."""
    global _is_online
    if _is_online:
        print("[SYNC] Marked OFFLINE dynamically by a route failure.")
        _is_online = False


# --------------------------------------------------------------------------
# Connectivity check
# --------------------------------------------------------------------------

async def check_online() -> bool:
    """Ping MongoDB to determine if we're online."""
    global _is_online
    try:
        from database import client
        if client is None:
            _is_online = False
            return False
        # server_info() with a short timeout
        await asyncio.wait_for(
            client.admin.command("ping"),
            timeout=PING_TIMEOUT_MS / 1000,
        )
        if not _is_online:
            print("[SYNC] MongoDB is ONLINE again!")
        _is_online = True
        return True
    except Exception:
        if _is_online:
            print("[SYNC] MongoDB is OFFLINE – switching to local cache.")
        _is_online = False
        return False


# --------------------------------------------------------------------------
# Push: local → remote
# --------------------------------------------------------------------------

async def sync_pending_orders() -> int:
    """Push pending offline orders to MongoDB. Returns count synced.

    For each order we:
    1. Insert the order document.
    2. Deduct stock on the remote ``products`` collection (bulk $inc).
    """
    orders_col = get_collection("orders")
    products_col = get_collection("products")
    pending = await local_db.pop_pending_orders()
    synced = 0
    for item in pending:
        try:
            doc = item["data"]
            # Convert created_at back to datetime if it's a string
            if isinstance(doc.get("created_at"), str):
                doc["created_at"] = datetime.fromisoformat(doc["created_at"])
            if "_id" in doc and isinstance(doc["_id"], str):
                from bson import ObjectId
                try:
                    doc["_id"] = ObjectId(doc["_id"])
                except Exception:
                    pass
            await orders_col.insert_one(doc)

            # Deduct stock on remote for every line item
            from pymongo import UpdateOne
            bulk_ops = []
            for line in doc.get("items", []):
                pid = line.get("product_id")
                qty = line.get("quantity", 0)
                if pid and qty > 0:
                    try:
                        from bson import ObjectId
                        oid = ObjectId(pid)
                    except Exception:
                        continue
                    bulk_ops.append(UpdateOne(
                        {"_id": oid},
                        {"$inc": {"stock": -qty}},
                    ))
            if bulk_ops:
                try:
                    await products_col.bulk_write(bulk_ops)
                except Exception as stock_err:
                    print(f"[SYNC] Stock deduction failed for order {doc.get('order_number')}: {stock_err}")

            await local_db.remove_pending_order(item["local_id"])
            synced += 1
        except Exception as e:
            print(f"[SYNC] Failed to sync order local_id={item['local_id']}: {e}")
            break  # Stop on first failure to preserve order
    return synced


async def sync_pending_drawer_txs() -> int:
    """Push pending drawer transactions to MongoDB. Returns count synced."""
    state_col = get_collection("drawer_state")
    tx_col = get_collection("drawer_transactions")
    pending = await local_db.pop_pending_drawer_txs()
    synced = 0
    for item in pending:
        try:
            doc = item["data"]
            amount = doc.get("amount", 0)
            if isinstance(doc.get("created_at"), str):
                doc["created_at"] = datetime.fromisoformat(doc["created_at"])
            # Update remote drawer state
            from pymongo import ReturnDocument
            await state_col.find_one_and_update(
                {"_id": "main_drawer"},
                {
                    "$inc": {"balance": amount},
                    "$set": {"last_updated": doc["created_at"]}
                },
                upsert=True,
            )
            # Insert transaction record
            await tx_col.insert_one(doc)
            await local_db.remove_pending_drawer_tx(item["local_id"])
            synced += 1
        except Exception as e:
            print(f"[SYNC] Failed to sync drawer tx local_id={item['local_id']}: {e}")
            break
    return synced


async def sync_pending_logs() -> int:
    """Push pending audit logs to MongoDB. Returns count synced."""
    logs_col = get_collection("system_logs")
    pending = await local_db.pop_pending_logs()
    synced = 0
    for item in pending:
        try:
            doc = item["data"]
            if isinstance(doc.get("timestamp"), str):
                doc["timestamp"] = datetime.fromisoformat(doc["timestamp"])
            await logs_col.insert_one(doc)
            await local_db.remove_pending_log(item["local_id"])
            synced += 1
        except Exception as e:
            print(f"[SYNC] Failed to sync log local_id={item['local_id']}: {e}")
            break
    return synced



async def sync_pending_preorder_fulfills() -> int:
    """Push pending offline preorder fulfills to MongoDB. Returns count synced.

    For each buffered fulfill we:
    1. Insert the order document into ``orders``.
    2. Deduct stock and release reserved stock on ``products``.
    3. Update the preorder status to ``fulfilled`` on ``preorders``.
    """
    orders_col = get_collection("orders")
    products_col = get_collection("products")
    preorders_col = get_collection("preorders")
    pending = await local_db.pop_pending_preorder_fulfills()
    synced = 0
    for item in pending:
        try:
            data = item["data"]
            order_doc = data["order_doc"]
            preorder_id = data["preorder_id"]
            barcode_code = data["barcode_code"]
            fulfilled_at = data.get("fulfilled_at")
            fulfilled_by = data.get("fulfilled_by")

            # Convert datetime strings
            if isinstance(order_doc.get("created_at"), str):
                order_doc["created_at"] = datetime.fromisoformat(order_doc["created_at"])

            # 1. Insert order
            result = await orders_col.insert_one(order_doc)
            order_id = str(result.inserted_id)

            # 2. Deduct stock + release reserved
            from pymongo import UpdateOne
            from bson import ObjectId
            bulk_ops = []
            for line in order_doc.get("items", []):
                pid = line.get("product_id")
                qty = line.get("quantity", 0)
                if pid and qty > 0:
                    try:
                        oid = ObjectId(pid)
                    except Exception:
                        continue
                    bulk_ops.append(UpdateOne(
                        {"_id": oid},
                        {"$inc": {"stock": -qty, "stock_reserved": -qty}},
                    ))
            if bulk_ops:
                try:
                    await products_col.bulk_write(bulk_ops)
                except Exception as e:
                    print(f"[SYNC] Stock deduction failed for fulfill {barcode_code}: {e}")

            # 3. Update preorder status on remote
            if isinstance(fulfilled_at, str):
                fulfilled_at_dt = datetime.fromisoformat(fulfilled_at)
            else:
                fulfilled_at_dt = fulfilled_at or datetime.now(timezone.utc)
            try:
                await preorders_col.find_one_and_update(
                    {"_id": ObjectId(preorder_id)},
                    {"$set": {
                        "status": "fulfilled",
                        "fulfilled_at": fulfilled_at_dt,
                        "fulfilled_by": fulfilled_by,
                        "order_id": order_id,
                    }},
                )
            except Exception as e:
                print(f"[SYNC] Failed to update preorder status for {barcode_code}: {e}")

            await local_db.remove_pending_preorder_fulfill(item["local_id"])
            synced += 1
        except Exception as e:
            print(f"[SYNC] Failed to sync preorder fulfill local_id={item['local_id']}: {e}")
            break
    return synced


async def push_all_pending() -> dict:
    """Push all pending data to MongoDB. Returns summary."""
    results = {
        "orders": await sync_pending_orders(),
        "drawer_txs": await sync_pending_drawer_txs(),
        "logs": await sync_pending_logs(),
        "preorder_fulfills": await sync_pending_preorder_fulfills(),
    }
    total = sum(results.values())
    if total > 0:
        print(f"[SYNC] Pushed {total} pending items → MongoDB: {results}")
    return results


# --------------------------------------------------------------------------
# Pull: remote → local
# --------------------------------------------------------------------------

async def sync_remote_to_local() -> None:
    """Download products, users, preorders, and recent orders from MongoDB into SQLite."""
    try:
        # Sync categories
        categories_col = get_collection("categories")
        cursor = categories_col.find({})
        categories = await cursor.to_list(length=1000)
        await local_db.cache_categories(categories)

        # Sync products
        products_col = get_collection("products")
        cursor = products_col.find({})
        products = await cursor.to_list(length=10000)
        await local_db.cache_products(products)

        # Sync users
        users_col = get_collection("users")
        cursor = users_col.find({})
        users = await cursor.to_list(length=1000)
        await local_db.cache_users(users)

        # Sync preorders (all non-cancelled — pending + fulfilled for lookup)
        preorders_col = get_collection("preorders")
        cursor = preorders_col.find({"status": {"$ne": "cancelled"}})
        preorders = await cursor.to_list(length=10000)
        await local_db.cache_preorders(preorders)

        # Sync recent orders (last 500 for offline history)
        orders_col = get_collection("orders")
        cursor = orders_col.find({}).sort("created_at", -1).limit(500)
        orders = await cursor.to_list(length=500)
        await local_db.cache_orders(orders)

        # Sync drawer state
        drawer_col = get_collection("drawer_state")
        drawer_doc = await drawer_col.find_one({"_id": "main_drawer"})
        if drawer_doc:
            await local_db.set_local_drawer_balance(drawer_doc.get("balance", 0))

        # Update sync timestamp
        await local_db.set_meta("last_sync", datetime.now(timezone.utc).isoformat())
        print("[SYNC] Remote → Local sync complete.")

    except MONGO_NETWORK_ERRORS as e:
        print(f"[SYNC] Cannot pull from remote (offline): {e}")
    except Exception as e:
        print(f"[SYNC] Error during remote→local sync: {e}")
        traceback.print_exc()


# --------------------------------------------------------------------------
# Main sync loop (background task)
# --------------------------------------------------------------------------

async def start_sync_loop() -> None:
    """Run the sync loop forever. Should be launched as an asyncio task."""
    print(f"[SYNC] Background sync loop started (interval: {SYNC_INTERVAL_SECONDS}s)")
    while True:
        try:
            sleep_time = SYNC_INTERVAL_SECONDS if _is_online else 5
            await asyncio.sleep(sleep_time)

            online = await check_online()

            if online:
                # Push any buffered data first
                await push_all_pending()
                # Then refresh local cache
                await sync_remote_to_local()
            else:
                pending = await local_db.get_pending_counts()
                if any(v > 0 for v in pending.values()):
                    print(f"[SYNC] Offline – pending items: {pending}")

        except asyncio.CancelledError:
            print("[SYNC] Sync loop cancelled.")
            break
        except Exception as e:
            print(f"[SYNC] Unexpected error in sync loop: {e}")
            traceback.print_exc()
            await asyncio.sleep(10)  # Back off on errors
