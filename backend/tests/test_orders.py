import pytest
from httpx import AsyncClient
from database import get_collection

pytestmark = pytest.mark.asyncio

@pytest.fixture
async def sample_products(async_client: AsyncClient, admin_token):
    # Create some products to use in orders
    products = []
    for i in range(1, 4):
        res = await async_client.post(
            "/api/products",
            json={"name": f"OrdProd {i}", "price": i * 10000, "stock": 100},
            headers=admin_token
        )
        products.append(res.json())
    return products

class TestOrderCreate:
    async def test_create_order_cash_success(self, async_client: AsyncClient, employee_token, sample_products):
        payload = {
            "items": [
                {"product_id": sample_products[0]["id"], "product_name": "P1", "price": 10000, "quantity": 2},
                {"product_id": sample_products[1]["id"], "product_name": "P2", "price": 20000, "quantity": 1}
            ],
            "payment_method": "cash",
            "amount_given": 50000,
            "expected_change": 8000,
            "actual_change": 8000
        }
        res = await async_client.post("/api/orders", json=payload, headers=employee_token)
        assert res.status_code == 201
        data = res.json()
        assert data["subtotal"] == 40000
        assert data["vat_rate"] == 5
        assert data["vat_amount"] == 2000
        assert data["total"] == 42000
        assert data["actual_revenue"] == 42000
        assert data["order_number"].startswith("ORD-")
        
        # Verify drawer state
        drawer_state = await get_collection("drawer_state").find_one({"_id": "main_drawer"})
        assert drawer_state["balance"] >= 42000
        
        # Verify stock deducted
        prod1 = await get_collection("products").find_one({"name": "OrdProd 1"})
        assert prod1["stock"] == 98 # 100 - 2

    async def test_create_order_transfer_success(self, async_client: AsyncClient, employee_token, sample_products):
        payload = {
            "items": [
                {"product_id": sample_products[0]["id"], "product_name": "P1", "price": 10000, "quantity": 1}
            ],
            "payment_method": "transfer"
        }
        # Drawer before
        drawer_before = await get_collection("drawer_state").find_one({"_id": "main_drawer"})
        bal_before = drawer_before["balance"] if drawer_before else 0
        
        res = await async_client.post("/api/orders", json=payload, headers=employee_token)
        assert res.status_code == 201
        
        # Drawer should not change for transfer
        drawer_after = await get_collection("drawer_state").find_one({"_id": "main_drawer"})
        bal_after = drawer_after["balance"] if drawer_after else 0
        assert bal_after == bal_before

    async def test_create_order_split_success(self, async_client: AsyncClient, employee_token, sample_products):
        payload = {
            "items": [
                {"product_id": sample_products[2]["id"], "product_name": "P3", "price": 30000, "quantity": 1}
            ],
            "payment_method": "split",
            "payments": [
                {"method": "cash", "amount": 10000},
                {"method": "transfer", "amount": 21500}
            ]
        }
        res = await async_client.post("/api/orders", json=payload, headers=employee_token)
        assert res.status_code == 201
        data = res.json()
        assert data["total"] == 31500

    @pytest.mark.parametrize("payments, expected_status", [
        ([{"method": "cash", "amount": 10000}, {"method": "transfer", "amount": 10000}], 400), # Not matching total (31500)
        ([], 400), # Empty payments
    ])
    async def test_create_order_split_validation(self, async_client: AsyncClient, employee_token, sample_products, payments, expected_status):
        payload = {
            "items": [{"product_id": sample_products[2]["id"], "product_name": "P3", "price": 30000, "quantity": 1}],
            "payment_method": "split",
            "payments": payments
        }
        res = await async_client.post("/api/orders", json=payload, headers=employee_token)
        assert res.status_code == expected_status

    @pytest.mark.parametrize("payload, expected_status", [
        ({"items": [], "payment_method": "cash"}, 422), # Empty items
        ({"items": [{"product_id": "1", "product_name": "P", "price": -10, "quantity": 1}], "payment_method": "cash"}, 422), # Negative price
        ({"items": [{"product_id": "1", "product_name": "P", "price": 10, "quantity": 0}], "payment_method": "cash"}, 422), # Zero quantity
        ({"items": [{"product_id": "1", "product_name": "P", "price": 10, "quantity": -5}], "payment_method": "cash"}, 422), # Negative quantity
        ({"items": [{"product_name": "P", "price": 10, "quantity": 1}], "payment_method": "cash"}, 422), # Missing product_id
        ({"items": [{"product_id": "1", "price": 10, "quantity": 1}], "payment_method": "cash"}, 422), # Missing product_name
        ({"items": [{"product_id": "1", "product_name": "P", "quantity": 1}], "payment_method": "cash"}, 422), # Missing price
        ({"items": [{"product_id": "1", "product_name": "P", "price": 10}], "payment_method": "cash"}, 422), # Missing quantity
    ])
    async def test_create_order_item_validation(self, async_client: AsyncClient, employee_token, payload, expected_status):
        res = await async_client.post("/api/orders", json=payload, headers=employee_token)
        assert res.status_code == expected_status

    @pytest.mark.parametrize("payment_method, expected_status", [
        ("invalid", 422),
        ("", 422),
        ("credit_card", 422), # Unrecognized if not in allowed list (assuming allowed is cash/transfer/split)
    ])
    async def test_create_order_invalid_payment_method(self, async_client: AsyncClient, employee_token, sample_products, payment_method, expected_status):
        payload = {
            "items": [{"product_id": sample_products[0]["id"], "product_name": "P1", "price": 10000, "quantity": 1}],
            "payment_method": payment_method
        }
        res = await async_client.post("/api/orders", json=payload, headers=employee_token)
        assert res.status_code == expected_status


class TestOrderRead:
    @pytest.fixture(autouse=True)
    async def setup_orders(self, async_client: AsyncClient, employee_token, sample_products):
        # Create 15 orders
        for i in range(15):
            await async_client.post("/api/orders", json={
                "items": [{"product_id": sample_products[0]["id"], "product_name": "P1", "price": 10000, "quantity": 1}],
                "payment_method": "cash"
            }, headers=employee_token)

    async def test_list_orders_pagination(self, async_client: AsyncClient, employee_token):
        res = await async_client.get("/api/orders?page=1&per_page=10", headers=employee_token)
        assert res.status_code == 200
        assert len(res.json()["items"]) == 10
        
        res2 = await async_client.get("/api/orders?page=2&per_page=10", headers=employee_token)
        assert len(res2.json()["items"]) >= 5

    async def test_list_orders_date_filter(self, async_client: AsyncClient, employee_token):
        from datetime import datetime
        today_str = datetime.now().strftime("%Y-%m-%d")
        res = await async_client.get(f"/api/orders?date={today_str}", headers=employee_token)
        assert res.status_code == 200
        assert len(res.json()["items"]) >= 15

    async def test_list_orders_date_filter_no_match(self, async_client: AsyncClient, employee_token):
        res = await async_client.get("/api/orders?date=2000-01-01", headers=employee_token)
        assert res.status_code == 200
        assert len(res.json()["items"]) == 0

    async def test_list_orders_invalid_date_format(self, async_client: AsyncClient, employee_token):
        res = await async_client.get("/api/orders?date=invalid-date", headers=employee_token)
        assert res.status_code == 422

    async def test_get_order_by_id_success(self, async_client: AsyncClient, employee_token):
        list_res = await async_client.get("/api/orders?per_page=1", headers=employee_token)
        order_id = list_res.json()["items"][0]["id"]
        
        res = await async_client.get(f"/api/orders/{order_id}", headers=employee_token)
        assert res.status_code == 200
        assert res.json()["id"] == order_id

    async def test_get_order_by_id_not_found(self, async_client: AsyncClient, employee_token):
        res = await async_client.get("/api/orders/5f9b3b9b9b9b9b9b9b9b9b9b", headers=employee_token)
        assert res.status_code == 404
