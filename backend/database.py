"""
EViENT POS - Database Module

Provides async MongoDB connection management using Motor (AsyncIOMotorClient).
Exposes helpers to get the database instance and individual collections.
"""

from motor.motor_asyncio import AsyncIOMotorClient

from config import settings

# Global database references
client: AsyncIOMotorClient | None = None
db = None


async def connect_db() -> None:
    """Create the async MongoDB client and bind the database.

    Reads MONGO_URI and DB_NAME from the application settings.
    Must be called once during application startup.
    """
    global client, db
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.DB_NAME]
    print(f"[DB] Connected to MongoDB: {settings.MONGO_URI}/{settings.DB_NAME}")


async def close_db() -> None:
    """Close the MongoDB client connection.

    Should be called during application shutdown to release resources.
    """
    global client
    if client is not None:
        client.close()
        print("[DB] MongoDB connection closed.")


def get_database():
    """Return the current database instance.

    Returns:
        The Motor database object. Will be ``None`` if ``connect_db()``
        has not been called yet.
    """
    return db


def get_collection(name: str):
    """Return a Motor collection by name.

    Args:
        name: The name of the MongoDB collection.

    Returns:
        The Motor collection object.

    Raises:
        RuntimeError: If the database has not been initialised.
    """
    if db is None:
        raise RuntimeError(
            "Database not initialised. Call connect_db() first."
        )
    return db[name]


def is_online() -> bool:
    """Return current MongoDB connectivity status (from sync_engine)."""
    try:
        from sync_engine import is_online as _sync_is_online
        return _sync_is_online()
    except ImportError:
        return True  # Assume online if sync_engine not loaded yet

