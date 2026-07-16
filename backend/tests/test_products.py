import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

class TestProductCreate:
    async def test_create_product_success(self, async_client: AsyncClient, admin_token, manager_token):
        for token in [admin_token, manager_token]:
            payload = {
                "name": f"Test Product {token}",
                "price": 1000,
                "stock": 10
            }
            res = await async_client.post("/api/products", json=payload, headers=token)
            assert res.status_code == 201
        assert res.json()["name"] == payload["name"]

    async def test_create_product_forbidden_employee(self, async_client: AsyncClient, employee_token):
        payload = {"name": "Test", "price": 10}
        res = await async_client.post("/api/products", json=payload, headers=employee_token)
        assert res.status_code == 403

    @pytest.mark.parametrize("payload, expected_status", [
        ({"price": 1000}, 422), # Missing name
        ({"name": "Test", "price": -100}, 422), # Negative price
        ({"name": "Test", "price": 10, "stock": -5}, 422), # Negative stock
        ({"name": "", "price": 10}, 422), # Empty name
    ])
    async def test_create_product_validation(self, async_client: AsyncClient, admin_token, payload, expected_status):
        res = await async_client.post("/api/products", json=payload, headers=admin_token)
        assert res.status_code == expected_status

    async def test_create_product_duplicate_barcode(self, async_client: AsyncClient, admin_token):
        payload = {"name": "Prod 1", "barcode": "DUP123", "price": 10}
        await async_client.post("/api/products", json=payload, headers=admin_token)
        
        res = await async_client.post("/api/products", json={"name": "Prod 2", "barcode": "DUP123", "price": 20}, headers=admin_token)
        assert res.status_code == 400
        assert "barcode" in res.json()["detail"].lower() and "exists" in res.json()["detail"].lower()


class TestProductRead:
    @pytest.fixture(autouse=True)
    async def setup_products(self, async_client: AsyncClient, admin_token):
        for i in range(1, 16):
            await async_client.post(
                "/api/products", 
                json={"name": f"Item {i}", "barcode": f"BC{i}", "price": i * 1000, "category": "General"}, 
                headers=admin_token
            )
    
    async def test_list_products_pagination(self, async_client: AsyncClient, employee_token):
        res = await async_client.get("/api/products?page=1&per_page=10", headers=employee_token)
        assert res.status_code == 200
        data = res.json()
        assert len(data["items"]) == 10
        assert data["total"] >= 15
        assert data["page"] == 1
        
        res2 = await async_client.get("/api/products?page=2&per_page=10", headers=employee_token)
        assert len(res2.json()["items"]) >= 5

    @pytest.mark.parametrize("query, expected_count", [
        ("Item 1", 7), # Item 1, 10, 11, 12, 13, 14, 15
        ("item 2", 1), # Case insensitive
        ("BC5", 1),    # Barcode search
        ("NotExists", 0)
    ])
    async def test_list_products_search(self, async_client: AsyncClient, employee_token, query, expected_count):
        res = await async_client.get(f"/api/products?q={query}", headers=employee_token)
        assert res.status_code == 200
        assert len(res.json()["items"]) == expected_count

    async def test_get_product_by_barcode_success(self, async_client: AsyncClient, employee_token):
        res = await async_client.get("/api/products/barcode/BC7", headers=employee_token)
        assert res.status_code == 200
        assert res.json()["name"] == "Item 7"

    async def test_get_product_by_barcode_not_found(self, async_client: AsyncClient, employee_token):
        res = await async_client.get("/api/products/barcode/INVALID", headers=employee_token)
        assert res.status_code == 404

    async def test_get_product_by_id_success(self, async_client: AsyncClient, employee_token):
        # Get one product id
        list_res = await async_client.get("/api/products?per_page=1", headers=employee_token)
        prod_id = list_res.json()["items"][0]["id"]
        
        res = await async_client.get(f"/api/products/{prod_id}", headers=employee_token)
        assert res.status_code == 200
        assert res.json()["id"] == prod_id

    async def test_get_product_by_id_not_found(self, async_client: AsyncClient, employee_token):
        res = await async_client.get("/api/products/5f9b3b9b9b9b9b9b9b9b9b9b", headers=employee_token)
        assert res.status_code == 404


class TestProductUpdateDelete:
    async def test_update_product_success(self, async_client: AsyncClient, admin_token):
        create_res = await async_client.post("/api/products", json={"name": "To Update", "price": 10}, headers=admin_token)
        prod_id = create_res.json()["id"]
        
        update_res = await async_client.put(f"/api/products/{prod_id}", json={"price": 999, "stock": 50}, headers=admin_token)
        assert update_res.status_code == 200
        assert update_res.json()["price"] == 999
        assert update_res.json()["stock"] == 50
        assert update_res.json()["name"] == "To Update" # Unchanged

    async def test_update_product_duplicate_barcode(self, async_client: AsyncClient, admin_token):
        await async_client.post("/api/products", json={"name": "A", "barcode": "BCA", "price": 10}, headers=admin_token)
        create_res = await async_client.post("/api/products", json={"name": "B", "barcode": "BCB", "price": 10}, headers=admin_token)
        prod_id = create_res.json()["id"]
        
        update_res = await async_client.put(f"/api/products/{prod_id}", json={"barcode": "BCA"}, headers=admin_token)
        assert update_res.status_code == 400

    async def test_update_product_forbidden_employee(self, async_client: AsyncClient, admin_token, employee_token):
        create_res = await async_client.post("/api/products", json={"name": "For Emp Update", "price": 10}, headers=admin_token)
        prod_id = create_res.json()["id"]
        
        res = await async_client.put(f"/api/products/{prod_id}", json={"price": 20}, headers=employee_token)
        assert res.status_code == 403

    @pytest.mark.parametrize("payload, expected_status", [
        ({"price": -100}, 422), # Negative price
        ({"stock": -5}, 422), # Negative stock
        ({"price": -10}, 422),
    ])
    async def test_update_product_validation(self, async_client: AsyncClient, admin_token, payload, expected_status):
        create_res = await async_client.post("/api/products", json={"name": "Validation Update", "price": 10}, headers=admin_token)
        prod_id = create_res.json()["id"]
        
        res = await async_client.put(f"/api/products/{prod_id}", json=payload, headers=admin_token)
        assert res.status_code == expected_status

    async def test_delete_product_success(self, async_client: AsyncClient, admin_token):
        create_res = await async_client.post("/api/products", json={"name": "To Delete", "price": 10}, headers=admin_token)
        prod_id = create_res.json()["id"]
        
        del_res = await async_client.delete(f"/api/products/{prod_id}", headers=admin_token)
        assert del_res.status_code == 200
        
        get_res = await async_client.get(f"/api/products/{prod_id}", headers=admin_token)
        assert get_res.status_code == 404

    async def test_delete_product_not_found(self, async_client: AsyncClient, admin_token):
        res = await async_client.delete("/api/products/5f9b3b9b9b9b9b9b9b9b9b9b", headers=admin_token)
        assert res.status_code == 404

    async def test_delete_product_forbidden_employee(self, async_client: AsyncClient, admin_token, employee_token):
        create_res = await async_client.post("/api/products", json={"name": "To Delete Emp", "price": 10}, headers=admin_token)
        prod_id = create_res.json()["id"]
        
        res = await async_client.delete(f"/api/products/{prod_id}", headers=employee_token)
        assert res.status_code == 403
