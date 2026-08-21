"""
EViENT POS - Order Routes

Endpoints:
    POST /orders/        – Create a new order.
    GET  /orders/        – List orders (paginated, filterable by date).
    GET  /orders/{id}    – Get a single order.
"""

from datetime import datetime, timezone
import asyncio

from pymongo import ReturnDocument, UpdateOne
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status, BackgroundTasks

from auth import get_current_user, require_role
from database import get_collection, is_online
from middleware import log_action
from models import OrderCreate, OrderResponse, PaginatedResponse
import local_db
import sync_engine

router = APIRouter(prefix="/orders", tags=["Orders"])


async def _generate_order_number() -> str:
    """Generate the next sequential order number for today.

    Format: ``ORD-YYYYMMDD-XXXX`` where XXXX is a zero-padded counter
    that resets daily.
    """
    today_str = datetime.now().astimezone().strftime("%Y%m%d")
    prefix = f"ORD-{today_str}-"

    counters = get_collection("counters")
    counter_doc = await counters.find_one_and_update(
        {"_id": f"order_number_{today_str}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    
    next_seq = counter_doc["seq"]

    return f"{prefix}{next_seq:04d}"


# --------------------------------------------------------------------------
# Create order
# --------------------------------------------------------------------------

from config import settings

@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    body: OrderCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_role("admin", "manager", "cashier", "employee")),
):
    """Create a new point-of-sale order.

    Automatically generates a sequential order number, calculates the
    total from the line items, and records the cashier.
    """
    # Validate stock_reserved vs requested quantity
    import local_db
    for item in body.items:
        prod = await local_db.get_cached_product_by_id(item.product_id)
        if prod:
            available = prod.get("stock", 0) - prod.get("stock_reserved", 0)
            if available < item.quantity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Sản phẩm '{prod.get('name')}' không đủ số lượng (Còn: {prod.get('stock', 0)}, Đã giữ: {prod.get('stock_reserved', 0)})."
                )

    subtotal = sum(item.price * item.quantity for item in body.items)
    vat_rate = settings.VAT_RATE
    vat_amount = subtotal * (vat_rate / 100)
    total = subtotal + vat_amount

    # --- Payment logic ---
    user_id = str(current_user["_id"])
    payment_method = body.payment_method
    payments_list = None
    actual_revenue = total

    if payment_method == "split":
        if not body.payments or len(body.payments) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Thanh toán chia tiền (split) yêu cầu chi tiết thanh toán.",
            )
        # Split payment
        payments_total = sum(p.amount for p in body.payments)
        if abs(payments_total - total) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tổng các khoản thanh toán ({payments_total:,.0f}) không khớp với tổng đơn ({total:,.0f}).",
            )
        payment_method = "split"
        payments_list = [p.model_dump() for p in body.payments]
        actual_revenue = total
    elif payment_method == "cash" and body.amount_given is not None and body.actual_change is not None:
        actual_revenue = body.amount_given - body.actual_change

    cash_added = 0
    if payment_method == "cash":
        cash_added = actual_revenue
    elif payment_method == "split" and body.payments:
        for p in body.payments:
            if p.method == "cash":
                cash_added += p.amount

    # ALWAYS use optimistic UI (offline-first approach)
    order_number = await local_db.next_offline_order_number()

    doc = {
        "order_number": order_number,
        "items": [item.model_dump() for item in body.items],
        "subtotal": round(subtotal, 2),
        "vat_rate": round(vat_rate, 2),
        "vat_amount": round(vat_amount, 2),
        "total": round(total, 2),
        "actual_revenue": round(actual_revenue, 2),
        "payment_method": payment_method,
        "payments": payments_list,
        "amount_given": body.amount_given,
        "expected_change": body.expected_change,
        "actual_change": body.actual_change,
        "cashier_id": user_id,
        "cashier_name": current_user.get("full_name", current_user["username"]),
        "created_at": datetime.now(timezone.utc),
    }

    doc["_id"] = ObjectId()
    await local_db.queue_order(doc)
    await local_db.save_single_order(doc) # Add to local read cache immediately
    
    if cash_added > 0:
        await local_db.update_local_drawer_balance(cash_added)
        await local_db.queue_drawer_tx({
            "amount": cash_added,
            "type": "sale",
            "note": f"Order {order_number} [OPTIMISTIC]",
            "user_id": str(current_user["_id"]),
            "username": current_user["username"],
            "created_at": doc["created_at"]
        })
    for item in body.items:
        await local_db.deduct_cached_stock(item.product_id, item.quantity)
        
    is_offline = True # For logging to mark as optimistic/offline

    # Trigger background sync immediately to push the queued order to MongoDB
    background_tasks.add_task(sync_engine.sync_pending_orders)

    # Audit log
    # Audit log
    client_ip = request.client.host if request.client else ""
    await log_action(
        action="CREATE_ORDER",
        user_id=str(current_user["_id"]),
        username=current_user["username"],
        details=(
            f"Created order {order_number} | "
            f"Total: {doc['total']:,.0f} | "
            f"Items: {len(body.items)} | "
            f"Payment: {body.payment_method}" + (" [OFFLINE]" if is_offline else "")
        ),
        ip_address=client_ip,
    )

    return OrderResponse.from_doc(doc)


# --------------------------------------------------------------------------
# List orders
# --------------------------------------------------------------------------

@router.get("", response_model=PaginatedResponse)
async def list_orders(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    date: str = Query(None, description="Filter by date (YYYY-MM-DD)"),
    current_user: dict = Depends(get_current_user),
):
    """Return a paginated list of orders, optionally filtered by date.

    The ``date`` query parameter accepts an ISO date string (``YYYY-MM-DD``)
    and returns orders created on that calendar day (UTC).
    """
    import local_db
    cached_items, total = await local_db.get_cached_orders(page, per_page, date)
    return PaginatedResponse.build(items=cached_items, total=total, page=page, per_page=per_page)


# --------------------------------------------------------------------------
# Single order
# --------------------------------------------------------------------------

@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return a single order by its ID."""
    orders = get_collection("orders")

    try:
        oid = ObjectId(order_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid order ID format.",
        )

    try:
        if not is_online():
            raise Exception("MongoDB is offline (fast fallback)")
            
        async def fetch_remote():
            return await orders.find_one({"_id": oid})
async def get_order(order_id: str, current_user: dict = Depends(get_current_user)):
    """Return a single order by its ID (Local-First)."""
    import local_db
    cached = await local_db.get_cached_order_by_id(order_id)
    if cached:
        return cached

    # If not in cache (e.g. very old order), try remote
    try:
        if not is_online():
            raise Exception("MongoDB is offline")
            
        async def fetch_remote():
            orders = get_collection("orders")
            return await orders.find_one({"_id": ObjectId(order_id)})
            
        doc = await asyncio.wait_for(fetch_remote(), timeout=2.0)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found (offline).",
        )

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found.",
        )

    return OrderResponse.from_doc(doc)
