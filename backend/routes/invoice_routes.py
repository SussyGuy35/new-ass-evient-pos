"""
EViENT POS - Invoice (Receipt) Routes

Renders a point-of-sale receipt as a PNG image using Pillow and returns
it via a streaming response.

Endpoints:
    GET /invoices/{order_id}/png – Generate and download a receipt image.
"""

import io
from datetime import timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from PIL import Image, ImageDraw, ImageFont

from auth import get_current_user
from database import get_collection

router = APIRouter(prefix="/invoices", tags=["Invoices"])


def _format_currency(value: float) -> str:
    """Format a number as a currency string (no symbol, with commas)."""
    return f"{value:,.0f}"


@router.get("/{order_id}/png")
async def get_invoice_png(
    order_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Render an order receipt as a PNG image.

    The image contains a header with the store name and order metadata,
    a table of line items, and a footer with payment / cashier details.
    Uses the default bitmap font shipped with Pillow.
    """
    orders = get_collection("orders")

    try:
        oid = ObjectId(order_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid order ID format.",
        )

    order = await orders.find_one({"_id": oid})
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found.",
        )

    # ------------------------------------------------------------------
    # Layout constants
    # ------------------------------------------------------------------
    WIDTH = 500
    MARGIN = 20
    LINE_HEIGHT = 20
    HEADER_HEIGHT = 120
    ITEM_HEADER_HEIGHT = 30
    FOOTER_HEIGHT = 100
    if order.get("payment_method") == "cash" and order.get("amount_given") is not None:
        FOOTER_HEIGHT += 40
    payments = order.get("payments")
    if order.get("payment_method") == "split" and payments:
        FOOTER_HEIGHT += len(payments) * 20 + 20

    items = order.get("items", [])
    num_items = len(items)
    content_height = num_items * LINE_HEIGHT
    total_height = HEADER_HEIGHT + ITEM_HEADER_HEIGHT + content_height + FOOTER_HEIGHT + MARGIN * 2

    # ------------------------------------------------------------------
    # Create image
    # ------------------------------------------------------------------
    img = Image.new("RGB", (WIDTH, total_height), color="white")
    draw = ImageDraw.Draw(img)
    try:
        import os
        font_path = os.path.join(os.path.dirname(__file__), "..", "assets", "Roboto-Regular.ttf")
        font = ImageFont.truetype(font_path, 14)
    except Exception:
        font = ImageFont.load_default()

    y = MARGIN

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    draw.text((WIDTH // 2 - 67, y), "THE NEW EViENT POS", fill="black", font=font)
    y += LINE_HEIGHT + 5

    draw.line([(MARGIN, y), (WIDTH - MARGIN, y)], fill="black", width=1)
    y += 10

    order_number = order.get("order_number", "N/A")
    draw.text((MARGIN, y), f"Order: {order_number}", fill="black", font=font)
    y += LINE_HEIGHT

    created_at = order.get("created_at")
    if created_at:
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        created_at_local = created_at.astimezone()
        date_str = created_at_local.strftime("%Y-%m-%d %H:%M:%S")
    else:
        date_str = "N/A"
    draw.text((MARGIN, y), f"Date: {date_str}", fill="black", font=font)
    y += LINE_HEIGHT

    cashier_name = order.get("cashier_name", "N/A")
    draw.text((MARGIN, y), f"Cashier: {cashier_name}", fill="black", font=font)
    y += LINE_HEIGHT + 5

    # ------------------------------------------------------------------
    # Item table header
    # ------------------------------------------------------------------
    draw.line([(MARGIN, y), (WIDTH - MARGIN, y)], fill="black", width=1)
    y += 5

    col_name = MARGIN
    col_qty = 270
    col_price = 330
    col_subtotal = 415

    draw.text((col_name, y), "Item", fill="black", font=font)
    draw.text((col_qty, y), "Qty", fill="black", font=font)
    draw.text((col_price, y), "Price", fill="black", font=font)
    draw.text((col_subtotal, y), "Total", fill="black", font=font)
    y += LINE_HEIGHT

    draw.line([(MARGIN, y), (WIDTH - MARGIN, y)], fill="gray", width=1)
    y += 5

    # ------------------------------------------------------------------
    # Item rows
    # ------------------------------------------------------------------
    for item in items:
        name = item.get("product_name", "Unknown")
        qty = item.get("quantity", 0)
        price = item.get("price", 0)
        subtotal = price * qty

        # Truncate long names
        display_name = name[:32] + ".." if len(name) > 34 else name

        draw.text((col_name, y), display_name, fill="black", font=font)
        draw.text((col_qty, y), str(qty), fill="black", font=font)
        draw.text((col_price, y), _format_currency(price), fill="black", font=font)
        draw.text((col_subtotal, y), _format_currency(subtotal), fill="black", font=font)
        y += LINE_HEIGHT

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------
    y += 5
    draw.line([(MARGIN, y), (WIDTH - MARGIN, y)], fill="black", width=2)
    y += 10

    total = order.get("total", 0)
    subtotal = order.get("subtotal")
    vat_rate = order.get("vat_rate", 0)
    vat_amount = order.get("vat_amount", 0)

    # Show subtotal and VAT if they exist and VAT is non-zero
    if subtotal is not None and vat_rate > 0:
        draw.text((MARGIN, y), f"SUBTOTAL: {_format_currency(subtotal)}", fill="black", font=font)
        y += LINE_HEIGHT
        draw.text((MARGIN, y), f"VAT ({vat_rate:g}%): {_format_currency(vat_amount)}", fill="black", font=font)
        y += LINE_HEIGHT
        
    draw.text((MARGIN, y), f"TOTAL: {_format_currency(total)}", fill="black", font=font)
    y += LINE_HEIGHT

    payment = order.get("payment_method", "cash").upper()
    payments = order.get("payments")

    if payment == "SPLIT" and payments:
        draw.text((MARGIN, y), "Payment: SPLIT", fill="black", font=font)
        y += LINE_HEIGHT
        for p in payments:
            method_label = p.get("method", "").upper()
            amount = p.get("amount", 0)
            draw.text((MARGIN + 10, y), f"- {method_label}: {_format_currency(amount)}", fill="black", font=font)
            y += LINE_HEIGHT
    else:
        draw.text((MARGIN, y), f"Payment: {payment}", fill="black", font=font)
        y += LINE_HEIGHT
    
    amount_given = order.get("amount_given")
    actual_change = order.get("actual_change")
    if payment == "CASH" and amount_given is not None and actual_change is not None:
        draw.text((MARGIN, y), f"Cash Given: {_format_currency(amount_given)}", fill="black", font=font)
        y += LINE_HEIGHT
        draw.text((MARGIN, y), f"Change: {_format_currency(actual_change)}", fill="black", font=font)
        y += LINE_HEIGHT

    y += 10

    draw.line([(MARGIN, y), (WIDTH - MARGIN, y)], fill="gray", width=1)
    y += 10
    draw.text(
        (WIDTH // 2 - 70, y),
        "Cảm ơn bạn và hẹn gặp lại!",
        fill="gray",
        font=font,
    )

    # ------------------------------------------------------------------
    # Return as streaming PNG
    # ------------------------------------------------------------------
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="image/png",
        headers={
            "Content-Disposition": f'inline; filename="receipt_{order_number}.png"',
        },
    )
