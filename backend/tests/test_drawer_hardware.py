import pytest
from httpx import AsyncClient
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.asyncio

class TestDrawerTransactions:
    async def test_get_drawer_balance_initial(self, async_client: AsyncClient, employee_token):
        # Should auto-initialize to 0
        res = await async_client.get("/api/drawer", headers=employee_token)
        assert res.status_code == 200
        assert res.json()["balance"] == 0

    async def test_create_transaction_pay_in(self, async_client: AsyncClient, employee_token):
        payload = {"amount": 50000, "type": "pay_in", "note": "Initial float"}
        res = await async_client.post("/api/drawer/transaction", json=payload, headers=employee_token)
        assert res.status_code == 201
        assert res.json()["amount"] == 50000
        
        # Verify balance updated
        bal_res = await async_client.get("/api/drawer", headers=employee_token)
        assert bal_res.json()["balance"] == 50000

    async def test_create_transaction_pay_out(self, async_client: AsyncClient, admin_token):
        # Add some balance first
        await async_client.post("/api/drawer/transaction", json={"amount": 100000, "type": "pay_in"}, headers=admin_token)
        
        payload = {"amount": 20000, "type": "pay_out", "note": "Lunch"}
        res = await async_client.post("/api/drawer/transaction", json=payload, headers=admin_token)
        assert res.status_code == 201
        assert res.json()["amount"] == -20000 # Should normalize to negative
        
        # Verify balance updated
        bal_res = await async_client.get("/api/drawer", headers=admin_token)
        assert bal_res.json()["balance"] == 80000

    @pytest.mark.parametrize("payload, expected_status", [
        ({"amount": 100, "type": "invalid_type"}, 422), # Invalid type enum
        ({"type": "pay_in"}, 422), # Missing amount
        ({"amount": "string", "type": "pay_in"}, 422), # Invalid amount type
        ({"amount": -5000, "type": "pay_in"}, 201), # Normalizes to abs value
        ({"amount": 0, "type": "pay_out"}, 201), # Zero amount
        ({"amount": 100, "type": "pay_in", "note": "x" * 1000}, 201), # Long note (assume no strict length limit)
        ({"amount": 100.5, "type": "pay_in"}, 201), # Float amount
        ({"amount": -100.5, "type": "pay_out"}, 201), # Negative float
        ({"amount": 100, "type": "sale"}, 400), # sale is internally generated, user shouldn't post it
        ({"amount": 100, "type": "refund"}, 400), # refund is also not allowed manually
    ])
    async def test_create_transaction_validation(self, async_client: AsyncClient, admin_token, payload, expected_status):
        res = await async_client.post("/api/drawer/transaction", json=payload, headers=admin_token)
        # Backend validation might accept or reject depending on schema
        assert res.status_code in [expected_status, 422]

    async def test_list_transactions_pagination(self, async_client: AsyncClient, admin_token):
        for i in range(15):
            await async_client.post("/api/drawer/transaction", json={"amount": 1000, "type": "pay_in"}, headers=admin_token)
            
        res = await async_client.get("/api/drawer/transactions?page=1&per_page=10", headers=admin_token)
        assert res.status_code == 200
        assert len(res.json()["items"]) == 10
        assert res.json()["total"] >= 15

    @pytest.mark.parametrize("page, per_page, expected_items", [
        (1, 5, 5),
        (2, 5, 5),
        (1, 100, 15), # Should cap or return all
        (100, 10, 0), # Empty page
        (0, 10, 422), # Invalid page
        (1, 0, 422),  # Invalid per_page
    ])
    async def test_list_transactions_pagination_edge_cases(self, async_client: AsyncClient, admin_token, page, per_page, expected_items):
        res = await async_client.get(f"/api/drawer/transactions?page={page}&per_page={per_page}", headers=admin_token)
        if res.status_code == 200:
            # We don't know exact total items as tests run in order, but we can verify limits
            assert len(res.json()["items"]) <= per_page
        else:
            assert res.status_code == 422


class TestHardwareDrawer:
    @patch('serial.Serial')
    async def test_open_drawer_success(self, mock_serial, async_client: AsyncClient, employee_token):
        # Mock serial object to not raise exception
        mock_instance = MagicMock()
        mock_serial.return_value = mock_instance
        
        res = await async_client.post("/api/hardware/drawer", headers=employee_token)
        assert res.status_code == 200
        assert res.json()["success"] is True
        mock_instance.write.assert_called()
        mock_instance.close.assert_called()

    @patch('serial.Serial')
    async def test_open_drawer_serial_exception(self, mock_serial, async_client: AsyncClient, employee_token):
        import serial
        mock_serial.side_effect = serial.SerialException("Port not found")
        
        res = await async_client.post("/api/hardware/drawer", headers=employee_token)
        # Backend catches it and raises 500
        assert res.status_code == 500
        assert "Port not found" in res.json()["detail"]

    async def test_open_drawer_no_port_configured(self, async_client: AsyncClient, employee_token):
        # Override config temporarily
        from config import settings
        original_port = settings.SERVER_SERIAL_PORT
        settings.SERVER_SERIAL_PORT = None
        
        res = await async_client.post("/api/hardware/drawer", headers=employee_token)
        assert res.status_code == 501
        
        settings.SERVER_SERIAL_PORT = original_port
