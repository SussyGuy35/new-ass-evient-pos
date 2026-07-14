"""
EViENT POS - Order Routes

Endpoints:
    POST /orders/        – Create a new order.
    GET  /orders/        – List orders (paginated, filterable by date).
    GET  /orders/{id}    – Get a single order.
"""

from datetime import datetime, timezone

from pymongo import ReturnDocument, UpdateOne
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from auth import get_current_user
from database import get_collection
from middleware import log_action
from models import OrderCreate, OrderResponse, PaginatedResponse

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
    current_user: dict = Depends(get_current_user),
):
    """Create a new point-of-sale order.

    Automatically generates a sequential order number, calculates the
    total from the line items, and records the cashier.
    """
    subtotal = sum(item.price * item.quantity for item in body.items)
    vat_rate = settings.VAT_RATE
    vat_amount = subtotal * (vat_rate / 100)
    total = subtotal + vat_amount
    order_number = await _generate_order_number()

    actual_revenue = total
    if body.payment_method == "cash" and body.amount_given is not None and body.actual_change is not None:
        actual_revenue = body.amount_given - body.actual_change

    doc = {
        "order_number": order_number,
        "items": [item.model_dump() for item in body.items],
        "subtotal": round(subtotal, 2),
        "vat_rate": round(vat_rate, 2),
        "vat_amount": round(vat_amount, 2),
        "total": round(total, 2),
        "actual_revenue": round(actual_revenue, 2),
        "payment_method": body.payment_method,
        "amount_given": body.amount_given,
        "expected_change": body.expected_change,
        "actual_change": body.actual_change,
        "cashier_id": str(current_user["_id"]),
        "cashier_name": current_user.get("full_name", current_user["username"]),
        "created_at": datetime.now(timezone.utc),
    }

    orders = get_collection("orders")
    result = await orders.insert_one(doc)
    doc["_id"] = result.inserted_id

    # Deduct stock for each product
    products_col = get_collection("products")
    bulk_ops = []
    for item in body.items:
        try:
            pid = ObjectId(item.product_id)
            bulk_ops.append(UpdateOne(
                {"_id": pid},
                {"$inc": {"stock": -item.quantity}}
            ))
        except Exception:
            pass
            
    if bulk_ops:
        try:
            await products_col.bulk_write(bulk_ops)
        except Exception:
            # Note: without transactions, this operation is still not fully atomic
            # but bulk_write minimizes the risk window.
            pass

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
            f"Payment: {body.payment_method}"
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
    orders = get_collection("orders")
    query_filter: dict = {}

    if date:
        try:
            day_start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            day_end = day_start.replace(
                hour=23, minute=59, second=59, microsecond=999999
            )
            query_filter["created_at"] = {"$gte": day_start, "$lte": day_end}
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format. Use YYYY-MM-DD.",
            )

    total = await orders.count_documents(query_filter)
    skip = (page - 1) * per_page

    cursor = (
        orders.find(query_filter)
        .sort("created_at", -1)
        .skip(skip)
        .limit(per_page)
    )
    docs = await cursor.to_list(length=per_page)

    items = [OrderResponse.from_doc(d).model_dump() for d in docs]
    return PaginatedResponse.build(items=items, total=total, page=page, per_page=per_page)


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

    doc = await orders.find_one({"_id": oid})
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found.",
        )

    return OrderResponse.from_doc(doc)
