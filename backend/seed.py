"""
EViENT POS - Database Seeder

Creates the default administrator account if it does not already exist.
Intended to run once on application startup.
"""

from datetime import datetime, timezone

from auth import hash_password
from database import get_collection


async def seed_admin() -> None:
    """Seed the default admin user (``evientadmin``) into the database.

    If the user already exists the function is a no-op and prints a skip
    message. Otherwise it creates the account with the pre-defined
    credentials and prints a success confirmation.
    """
    users = get_collection("users")

    existing = await users.find_one({"username": "evientadmin"})
    if existing is not None:
        print("[SEED] Admin account 'evientadmin' already exists – skipping.")
        return

    admin_doc = {
        "username": "evientadmin",
        "password": hash_password("@dmin123"),
        "full_name": "System Administrator",
        "role": "admin",
        "created_at": datetime.now(timezone.utc),
    }

    await users.insert_one(admin_doc)
    print("[SEED] Admin account 'evientadmin' created successfully.")
