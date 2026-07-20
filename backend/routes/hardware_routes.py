"""
EViENT POS - Hardware Routes

Endpoints:
    POST /hardware/drawer - Opens the cash drawer via the server's serial port.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from auth import get_current_user
from config import settings

router = APIRouter(prefix="/hardware", tags=["Hardware"])


class DrawerResponse(BaseModel):
    message: str
    success: bool


@router.post("/drawer", response_model=DrawerResponse)
async def open_drawer(current_user: dict = Depends(get_current_user)):
    """Open the cash drawer connected to the server.
    
    Requires SERVER_SERIAL_PORT to be configured in the environment.
    Uses the pyserial library to communicate with the hardware.
    """
    if not settings.SERVER_SERIAL_PORT:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Server serial port is not configured. Please set SERVER_SERIAL_PORT in .env.",
        )

    try:
        import serial
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="pyserial library is not installed on the server.",
        )

    try:
        # Open serial port
        ser = serial.Serial(
            port=settings.SERVER_SERIAL_PORT,
            baudrate=settings.BAUD_RATE,
            timeout=2
        )
        
        # Send command
        command_bytes = settings.CASH_DRAWER_COMMAND.encode('latin1')
        ser.write(command_bytes)
        
        # Close connection
        ser.close()
        
        return DrawerResponse(message="Cash drawer opened successfully.", success=True)
    except serial.SerialException as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Serial port error: {e}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to open cash drawer: {e}",
        )


@router.post("/print_receipt/{order_id}")
async def print_receipt(order_id: str, current_user: dict = Depends(get_current_user)):
    """Print an order receipt using the ESC/POS thermal printer."""
    if not settings.SERVER_SERIAL_PORT:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Server serial port is not configured.",
        )

    try:
        from escpos.printer import Serial
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="python-escpos library is not installed.",
        )

    # Fetch order
    from database import get_collection
    from bson import ObjectId
    import local_db

    orders_col = get_collection("orders")
    order = None
    try:
        oid = ObjectId(order_id)
        order = await orders_col.find_one({"_id": oid})
    except Exception:
        pass

    if not order:
        order = await local_db.get_pending_order_by_id(order_id)

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    try:
        p = Serial(devfile=settings.SERVER_SERIAL_PORT, baudrate=settings.BAUD_RATE, timeout=2)
        
        # Header
        p.set(align="center", bold=True, text_type="B")
        p.text("THE NEW EViENT POS\n")
        p.set(align="center", bold=False, text_type="A")
        p.text("123 POS Street, Tech City\n")
        p.text("Tel: 0123.456.789\n")
        p.text("--------------------------------\n")
        
        # Info
        p.set(align="left")
        p.text(f"Order: {order.get('order_number')}\n")
        p.text(f"Cashier: {order.get('cashier_name')}\n")
        date_str = order.get("created_at")
        if isinstance(date_str, str):
            date_str = date_str[:19].replace("T", " ")
        p.text(f"Date: {date_str}\n")
        p.text("--------------------------------\n")
        
        # Items
        for item in order.get("items", []):
            qty = item.get("quantity", 1)
            name = item.get("name", "Item")[:20]
            price = item.get("price", 0)
            total = qty * price
            p.text(f"{name:<20} {qty}x\n")
            p.text(f"{price:>15,.0f} {total:>15,.0f}\n")
        
        p.text("--------------------------------\n")
        
        # Totals
        p.set(align="right")
        p.text(f"Subtotal: {order.get('subtotal', 0):,.0f} VND\n")
        if order.get("vat_amount", 0) > 0:
            p.text(f"VAT: {order.get('vat_amount'):,.0f} VND\n")
        
        p.set(bold=True)
        p.text(f"TOTAL: {order.get('total', 0):,.0f} VND\n")
        p.set(bold=False)
        
        p.text(f"Payment: {str(order.get('payment_method')).upper()}\n")
        if order.get("payment_method") == "cash" and order.get("amount_given"):
            p.text(f"Amount Given: {order.get('amount_given'):,.0f} VND\n")
            p.text(f"Change: {order.get('actual_change', 0):,.0f} VND\n")
            
        p.text("--------------------------------\n")
        p.set(align="center")
        p.text("Thank you & See you again!\n\n\n\n")
        
        p.cut()
        p.close()
        
        return {"message": "Receipt printed successfully.", "success": True}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to print receipt: {e}"
        )
