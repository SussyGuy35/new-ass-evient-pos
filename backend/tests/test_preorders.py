import io
import pytest
from httpx import AsyncClient
from unittest.mock import patch
from database import get_collection

pytestmark = pytest.mark.asyncio

@pytest.fixture
async def sample_products(async_client: AsyncClient, admin_token):
    # Create some products directly in the db
    products_col = get_collection("products")
    products = [
        {"name": "Prod 1", "price": 10000, "stock": 10},
        {"name": "Prod 2", "price": 20000, "stock": 10},
        {"name": "Prod 3", "price": 30000, "stock": 10}
    ]
    res = await products_col.insert_many(products)
    
    # Return as list of dicts with 'id' mapped
    out = []
    for p in products:
        p["id"] = str(p["_id"])
        out.append(p)
    return out

class TestPreOrderImport:
    @patch("routes.preorder_routes.send_preorder_email")
    async def test_import_csv_success(self, mock_send_email, async_client: AsyncClient, admin_token, sample_products):
        mock_send_email.return_value = True

        csv_content = """customer_name,email,product_name,quantity
Nguyen Van A,nva@example.com,Prod 1,2
Nguyen Van A,nva@example.com,Prod 2,1
Tran Thi B,ttb@example.com,Prod 3,3
"""
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}

        res = await async_client.post(
            "/api/preorders/import-csv",
            files=files,
            headers=admin_token
        )
        data = res.json()
        assert res.status_code == 200
        assert data["success"] == 2
        assert len(data["errors"]) == 0
        assert len(data["preorders"]) == 2

        # Verify first preorder (Nguyen Van A)
        po_a = next(po for po in data["preorders"] if po["email"] == "nva@example.com")
        assert len(po_a["items"]) == 2
        assert po_a["subtotal"] == 40000
        assert po_a["status"] == "pending"

        # Verify second preorder (Tran Thi B)
        po_b = next(po for po in data["preorders"] if po["email"] == "ttb@example.com")
        assert len(po_b["items"]) == 1
        assert po_b["subtotal"] == 90000
        assert po_b["status"] == "pending"

        # Check that email function was called
        assert mock_send_email.call_count == 2

    @patch("routes.preorder_routes.send_preorder_email")
    async def test_import_csv_invalid_products(self, mock_send_email, async_client: AsyncClient, admin_token):
        csv_content = """customer_name,email,product_name,quantity
Test User,test@example.com,NonExistent Product,1
"""
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}

        res = await async_client.post(
            "/api/preorders/import-csv",
            files=files,
            headers=admin_token
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] == 0
        assert len(data["errors"]) == 2
        assert "Không tìm thấy sản phẩm" in data["errors"][0]

    async def test_import_preorders_invalid_file(self, async_client: AsyncClient, admin_token):
        res = await async_client.post(
            "/api/preorders/import-csv",
            files={"file": ("test.txt", b"not a csv", "text/plain")},
            headers=admin_token,
        )
        assert res.status_code == 400

    async def test_create_preorder_manual(self, async_client: AsyncClient, admin_token):
        # Create a product first
        product_res = await async_client.post(
            "/api/products",
            json={"name": "Manual Product", "price": 10.0, "stock": 10},
            headers=admin_token
        )
        product_id = product_res.json()["id"]

        # Create preorder manually
        res = await async_client.post(
            "/api/preorders",
            json={
                "customer_name": "Test Manual",
                "email": "test@example.com",
                "items": [
                    {"product_id": product_id, "quantity": 2}
                ]
            },
            headers=admin_token
        )
        assert res.status_code == 201
        data = res.json()
        assert data["customer_name"] == "Test Manual"
        assert len(data["items"]) == 1
        assert data["items"][0]["product_id"] == product_id
        assert data["subtotal"] == 20.0

class TestPreOrderFlow:
    @pytest.fixture
    @patch("routes.preorder_routes.send_preorder_email")
    async def created_preorder(self, mock_send_email, async_client: AsyncClient, admin_token, sample_products):
        mock_send_email.return_value = True
        csv_content = """customer_name,email,product_name,quantity
Cus A,cusa@example.com,Prod 1,2
"""
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
        res = await async_client.post("/api/preorders/import-csv", files=files, headers=admin_token)
        return res.json()["preorders"][0]

    async def test_list_preorders(self, async_client: AsyncClient, admin_token, created_preorder):
        res = await async_client.get("/api/preorders", headers=admin_token)
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == created_preorder["id"]

    async def test_lookup_preorder(self, async_client: AsyncClient, employee_token, created_preorder):
        barcode = created_preorder["barcode_code"]
        res = await async_client.get(f"/api/preorders/lookup/{barcode}", headers=employee_token)
        assert res.status_code == 200
        assert res.json()["barcode_code"] == barcode

    async def test_fulfill_preorder_success(self, async_client: AsyncClient, employee_token, created_preorder):
        barcode = created_preorder["barcode_code"]

        # Stock before
        prod_before = await get_collection("products").find_one({"name": "Prod 1"})
        stock_before = prod_before["stock"]

        # Fulfill
        res = await async_client.post(f"/api/preorders/fulfill/{barcode}", headers=employee_token)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "fulfilled"
        assert data["order_id"] is not None

        # Stock after
        prod_after = await get_collection("products").find_one({"name": "Prod 1"})
        assert prod_after["stock"] == stock_before - 2

        # Check order created
        from bson import ObjectId
        order_doc = await get_collection("orders").find_one({"_id": ObjectId(data["order_id"])})
        assert order_doc is not None
        assert order_doc["payment_method"] == "transfer"
        assert order_doc["total"] == created_preorder["total"]

    async def test_cancel_preorder(self, async_client: AsyncClient, admin_token, created_preorder):
        preorder_id = created_preorder["id"]

        # Cancel (only admin)
        res = await async_client.delete(f"/api/preorders/{preorder_id}", headers=admin_token)
        assert res.status_code == 200

        # Check status updated
        from bson import ObjectId
        doc = await get_collection("preorders").find_one({"_id": ObjectId(preorder_id)})
        assert doc["status"] == "cancelled"

    async def test_employee_cannot_cancel(self, async_client: AsyncClient, employee_token, created_preorder):
        preorder_id = created_preorder["id"]
        res = await async_client.delete(f"/api/preorders/{preorder_id}", headers=employee_token)
        assert res.status_code == 403
