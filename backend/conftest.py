import asyncio
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

from config import settings
from database import close_db, connect_db, get_collection
from main import app
from seed import seed_admin
from auth import create_access_token


@pytest_asyncio.fixture(autouse=True)
async def db_setup():
    """Connect to test database and clean it up before each test."""
    await connect_db()
    
    # Clean specific collections
    collections_to_clear = ["products", "orders", "system_logs", "counters", "drawer_state", "drawer_transactions", "users"]
    for coll in collections_to_clear:
        await get_collection(coll).delete_many({})
        
    # Initialize SQLite offline buffer for tests
    import local_db
    await local_db.init_db()
        
    # Seed the admin user
    await seed_admin()
    
    yield
    
    await local_db.close_db()
    await close_db()


@pytest_asyncio.fixture
async def async_client():
    """Provides an AsyncClient for FastAPI."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client


@pytest_asyncio.fixture
async def admin_token(async_client):
    """Returns headers with a valid admin token."""
    users = get_collection("users")
    admin = await users.find_one({"username": "evientadmin"})
    token = create_access_token({"user_id": str(admin["_id"])})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def manager_token(async_client):
    """Creates a manager user and returns auth headers."""
    users = get_collection("users")
    res = await users.insert_one({
        "username": "testmanager",
        "password": "hashed_pw",
        "full_name": "Test Manager",
        "role": "manager"
    })
    token = create_access_token({"user_id": str(res.inserted_id)})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def employee_token(async_client):
    """Creates an employee user and returns auth headers."""
    users = get_collection("users")
    res = await users.insert_one({
        "username": "testemployee",
        "password": "hashed_pw",
        "full_name": "Test Employee",
        "role": "employee"
    })
    token = create_access_token({"user_id": str(res.inserted_id)})
    return {"Authorization": f"Bearer {token}"}
