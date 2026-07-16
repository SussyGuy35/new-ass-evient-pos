import pytest
from httpx import AsyncClient
from database import get_collection
from datetime import datetime, timezone, timedelta
import random

pytestmark = pytest.mark.asyncio

class TestSystemLogs:
    @pytest.fixture(autouse=True)
    async def setup_logs(self):
        logs = get_collection("system_logs")
        await logs.delete_many({}) # Clear logs
        
        # Insert 15 dummy logs
        for i in range(15):
            await logs.insert_one({
                "action": "TEST_ACTION",
                "user_id": "test_user",
                "username": "tester",
                "details": f"Log {i}",
                "ip_address": "127.0.0.1",
                "timestamp": datetime.now(timezone.utc) - timedelta(minutes=i)
            })

    async def test_list_logs_admin(self, async_client: AsyncClient, admin_token):
        res = await async_client.get("/api/logs?page=1&per_page=10", headers=admin_token)
        assert res.status_code == 200
        assert len(res.json()["items"]) == 10
        assert res.json()["total"] >= 15

    async def test_list_logs_forbidden(self, async_client: AsyncClient, manager_token, employee_token):
        for token in [manager_token, employee_token]:
            res = await async_client.get("/api/logs", headers=token)
            assert res.status_code == 403

    @pytest.mark.parametrize("page, per_page, expected_status", [
        (1, 5, 200),
        (0, 10, 422), # Invalid page
        (1, 0, 422),  # Invalid per_page
        (100, 10, 200), # Empty page
    ])
    async def test_list_logs_pagination_validation(self, async_client: AsyncClient, admin_token, page, per_page, expected_status):
        res = await async_client.get(f"/api/logs?page={page}&per_page={per_page}", headers=admin_token)
        assert res.status_code == expected_status


class TestReports:
    @pytest.fixture(autouse=True)
    async def setup_report_data(self, async_client: AsyncClient, admin_token):
        # Create products
        p1 = await async_client.post("/api/products", json={"name": "Rep 1", "price": 1000, "stock": 100}, headers=admin_token)
        p1_id = p1.json()["id"]
        
        # Create orders for aggregations
        # 1 cash order
        await async_client.post("/api/orders", json={
            "items": [{"product_id": p1_id, "product_name": "Rep 1", "price": 1000, "quantity": 10}],
            "payment_method": "cash"
        }, headers=admin_token)
        
        # 1 transfer order
        await async_client.post("/api/orders", json={
            "items": [{"product_id": p1_id, "product_name": "Rep 1", "price": 1000, "quantity": 5}],
            "payment_method": "transfer"
        }, headers=admin_token)

        # 1 split order
        await async_client.post("/api/orders", json={
            "items": [{"product_id": p1_id, "product_name": "Rep 1", "price": 1000, "quantity": 10}],
            "payment_method": "split",
            "payments": [{"method": "cash", "amount": 5000}, {"method": "transfer", "amount": 5500}] # Includes 500 VAT
        }, headers=admin_token)

    async def test_dashboard_stats_success(self, async_client: AsyncClient, admin_token, manager_token):
        for token in [admin_token, manager_token]:
            res = await async_client.get("/api/reports/dashboard", headers=token)
            assert res.status_code == 200
            
            data = res.json()
        assert "today" in data
        assert "all_time" in data
        assert "top_products" in data
        
        # Check all_time stats
        assert data["all_time"]["orders"] >= 3
        # Total revenue = 10500 (cash) + 5250 (transfer) + 10500 (split) = 26250
        assert data["all_time"]["revenue"] >= 26250
        assert data["all_time"]["cash_revenue"] >= 15500 # 10500 + 5000
        assert data["all_time"]["transfer_revenue"] >= 10750 # 5250 + 5500

    async def test_dashboard_stats_forbidden(self, async_client: AsyncClient, employee_token):
        res = await async_client.get("/api/reports/dashboard", headers=employee_token)
        assert res.status_code == 403


class TestInvoices:
    async def test_get_invoice_png_success(self, async_client: AsyncClient, employee_token):
        # Create an order
        p_res = await async_client.get("/api/products?per_page=1", headers=employee_token)
        if len(p_res.json()["items"]) == 0:
            pytest.skip("No products found")
        p_id = p_res.json()["items"][0]["id"]
        
        o_res = await async_client.post("/api/orders", json={
            "items": [{"product_id": p_id, "product_name": "Test", "price": 1000, "quantity": 1}],
            "payment_method": "cash"
        }, headers=employee_token)
        order_id = o_res.json()["id"]
        
        # Get PNG
        png_res = await async_client.get(f"/api/invoices/{order_id}/png", headers=employee_token)
        assert png_res.status_code == 200
        assert png_res.headers["content-type"] == "image/png"
        assert len(png_res.content) > 100 # Should contain image bytes

    async def test_get_invoice_png_not_found(self, async_client: AsyncClient, employee_token):
        res = await async_client.get("/api/invoices/5f9b3b9b9b9b9b9b9b9b9b9b/png", headers=employee_token)
        assert res.status_code == 404

    @pytest.mark.parametrize("method, payload", [
        ("cash", {"payment_method": "cash", "amount_given": 50000}),
        ("transfer", {"payment_method": "transfer"}),
        ("split", {"payment_method": "split", "payments": [{"method": "cash", "amount": 500}, {"method": "transfer", "amount": 550}]}) # Assume 1000+50 VAT=1050
    ])
    async def test_get_invoice_different_payment_methods(self, async_client: AsyncClient, admin_token, method, payload):
        p_res = await async_client.post("/api/products", json={"name": "Inv Prod", "price": 1000}, headers=admin_token)
        p_id = p_res.json()["id"]
        
        order_data = {
            "items": [{"product_id": p_id, "product_name": "Test", "price": 1000, "quantity": 1}]
        }
        order_data.update(payload)
        
        o_res = await async_client.post("/api/orders", json=order_data, headers=admin_token)
        assert o_res.status_code == 201
        
        png_res = await async_client.get(f"/api/invoices/{o_res.json()['id']}/png", headers=admin_token)
        assert png_res.status_code == 200
        assert png_res.headers["content-type"] == "image/png"
