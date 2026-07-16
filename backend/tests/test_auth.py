import os
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient
from database import get_collection

pytestmark = pytest.mark.asyncio


class TestLogin:
    @pytest.mark.parametrize("username, password, expected_status", [
        ("evientadmin", "@dmin123", 200),  # Valid login
        ("evientadmin", "wrongpass", 401),  # Invalid password
        ("not_exist", "any_pass", 401),     # Invalid username
        ("", "@dmin123", 401),              # Missing username (validation)
        ("evientadmin", "", 401),           # Missing password (validation)
    ])
    async def test_login_variants(self, async_client: AsyncClient, username, password, expected_status):
        response = await async_client.post(
            "/api/auth/login",
            json={"username": username, "password": password}
        )
        assert response.status_code == expected_status
        if expected_status == 200:
            assert "access_token" in response.json()
            assert response.json()["user"]["username"] == username

    async def test_login_creates_audit_log(self, async_client: AsyncClient):
        logs = get_collection("system_logs")
        count_before = await logs.count_documents({"action": "LOGIN", "username": "evientadmin"})
        
        await async_client.post(
            "/api/auth/login",
            json={"username": "evientadmin", "password": "@dmin123"}
        )
        
        count_after = await logs.count_documents({"action": "LOGIN", "username": "evientadmin"})
        assert count_after == count_before + 1


class TestGetMe:
    async def test_get_me_success(self, async_client: AsyncClient, admin_token):
        response = await async_client.get("/api/auth/me", headers=admin_token)
        assert response.status_code == 200
        assert response.json()["username"] == "evientadmin"

    @pytest.mark.parametrize("headers, expected_status", [
        ({}, 401),  # Missing token
        ({"Authorization": "Bearer invalid_token_123"}, 401),  # Invalid token
        ({"Authorization": "InvalidFormat token"}, 401),  # Invalid format
    ])
    async def test_get_me_invalid_auth(self, async_client: AsyncClient, headers, expected_status):
        response = await async_client.get("/api/auth/me", headers=headers)
        assert response.status_code == expected_status


class TestUserManagement:
    async def test_list_users_admin(self, async_client: AsyncClient, admin_token):
        response = await async_client.get("/api/auth/users", headers=admin_token)
        assert response.status_code == 200
        assert "items" in response.json()
        assert len(response.json()["items"]) >= 1  # At least admin exists

    async def test_list_users_forbidden(self, async_client: AsyncClient, manager_token, employee_token):
        for token in [manager_token, employee_token]:
            res = await async_client.get("/api/auth/users", headers=token)
            assert res.status_code == 403

    async def test_create_user_admin_success(self, async_client: AsyncClient, admin_token):
        payload = {
            "username": "newuser",
            "password": "password123",
            "full_name": "New User",
            "role": "manager"
        }
        response = await async_client.post("/api/auth/users", json=payload, headers=admin_token)
        assert response.status_code == 201
        assert response.json()["username"] == "newuser"

    @pytest.mark.parametrize("payload, expected_status", [
        ({"username": "u", "password": "password123", "full_name": "User", "role": "employee"}, 422),  # Username too short
        ({"username": "user123!", "password": "password123", "full_name": "User", "role": "employee"}, 422), # Invalid chars
        ({"username": "user123", "password": "123", "full_name": "User", "role": "employee"}, 422),  # Password too short
        ({"username": "user123", "password": "password123", "full_name": "", "role": "employee"}, 422),  # Full name empty
        ({"username": "user123", "password": "password123", "full_name": "User", "role": "superadmin"}, 422),  # Invalid role
    ])
    async def test_create_user_validation(self, async_client: AsyncClient, admin_token, payload, expected_status):
        response = await async_client.post("/api/auth/users", json=payload, headers=admin_token)
        assert response.status_code == expected_status

    async def test_create_user_duplicate_username(self, async_client: AsyncClient, admin_token):
        payload = {"username": "evientadmin", "password": "password", "full_name": "Clone", "role": "admin"}
        response = await async_client.post("/api/auth/users", json=payload, headers=admin_token)
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"].lower()

    async def test_get_user_success(self, async_client: AsyncClient, admin_token):
        # Get admin id first
        res = await async_client.get("/api/auth/me", headers=admin_token)
        user_id = res.json()["id"]
        
        response = await async_client.get(f"/api/auth/users/{user_id}", headers=admin_token)
        assert response.status_code == 200
        assert response.json()["id"] == user_id

    async def test_get_user_not_found(self, async_client: AsyncClient, admin_token):
        response = await async_client.get("/api/auth/users/5f9b3b9b9b9b9b9b9b9b9b9b", headers=admin_token)
        assert response.status_code == 404

    async def test_update_user_success(self, async_client: AsyncClient, admin_token):
        # Create a user first
        create_res = await async_client.post(
            "/api/auth/users", 
            json={"username": "toupdate", "password": "password", "full_name": "Update Me", "role": "employee"}, 
            headers=admin_token
        )
        user_id = create_res.json()["id"]
        
        # Update
        update_res = await async_client.put(
            f"/api/auth/users/{user_id}",
            json={"full_name": "Updated Name", "role": "manager"},
            headers=admin_token
        )
        assert update_res.status_code == 200
        assert update_res.json()["full_name"] == "Updated Name"
        assert update_res.json()["role"] == "manager"

    async def test_delete_user_success(self, async_client: AsyncClient, admin_token):
        # Create user to delete
        create_res = await async_client.post(
            "/api/auth/users", 
            json={"username": "todelete", "password": "password", "full_name": "Delete Me", "role": "employee"}, 
            headers=admin_token
        )
        user_id = create_res.json()["id"]
        
        delete_res = await async_client.delete(f"/api/auth/users/{user_id}", headers=admin_token)
        assert delete_res.status_code == 200
        
        # Verify deletion
        get_res = await async_client.get(f"/api/auth/users/{user_id}", headers=admin_token)
        assert get_res.status_code == 404

    async def test_delete_user_prevent_self_delete(self, async_client: AsyncClient, admin_token):
        res = await async_client.get("/api/auth/me", headers=admin_token)
        user_id = res.json()["id"]
        
        delete_res = await async_client.delete(f"/api/auth/users/{user_id}", headers=admin_token)
        assert delete_res.status_code == 400
        assert "cannot delete your own account" in delete_res.json()["detail"].lower()


class TestEndShift:
    async def test_end_shift_success(self, async_client: AsyncClient, employee_token):
        # Manually insert a LOGIN log for the test employee
        logs = get_collection("system_logs")
        users = get_collection("users")
        emp = await users.find_one({"username": "testemployee"})
        
        await logs.insert_one({
            "action": "LOGIN",
            "user_id": str(emp["_id"]),
            "username": "testemployee",
            "details": "Login successful.",
            "ip_address": "127.0.0.1",
            "timestamp": datetime.now(timezone.utc)
        })
        
        response = await async_client.post("/api/auth/shift/end", headers=employee_token)
        assert response.status_code == 200
        assert "message" in response.json()

    async def test_end_shift_no_login_found(self, async_client: AsyncClient, admin_token):
        # Ensure no login logs exist for a new user, or clear them
        logs = get_collection("system_logs")
        await logs.delete_many({"action": "LOGIN", "username": "evientadmin"})
        response = await async_client.post("/api/auth/shift/end", headers=admin_token)
        assert response.status_code == 400
        assert "No login record found" in response.json()["detail"]
