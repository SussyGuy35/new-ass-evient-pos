"""
EViENT POS - Middleware / Logging Utilities

Provides an ``log_action`` helper that writes audit-log entries to the
``system_logs`` MongoDB collection with a UTC timestamp.
"""

from datetime import datetime, timezone

from database import get_collection


async def log_action(
    action: str,
    user_id: str,
    username: str,
    details: str,
    ip_address: str = "",
) -> None:
    """Record an audit-log entry in the ``system_logs`` collection.

    Args:
        action: Short label for the action (e.g. ``"LOGIN"``, ``"CREATE_PRODUCT"``).
        user_id: The ID (string) of the user who performed the action.
        username: The username of the actor.
        details: Human-readable description of what happened.
        ip_address: The client IP address (optional).
    """
    try:
        logs = get_collection("system_logs")
        await logs.insert_one(
            {
                "action": action,
                "user_id": user_id,
                "username": username,
                "details": details,
                "ip_address": ip_address,
                "timestamp": datetime.now(timezone.utc),
            }
        )
    except Exception as exc:
        # MongoDB is down – buffer to local SQLite
        print(f"[LOG] MongoDB unavailable, buffering log locally: {exc}")
        try:
            import local_db
            await local_db.queue_log({
                "action": action,
                "user_id": user_id,
                "username": username,
                "details": details,
                "ip_address": ip_address,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as local_exc:
            print(f"[LOG ERROR] Failed to buffer log locally: {local_exc}")
