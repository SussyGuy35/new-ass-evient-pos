"""
EViENT POS - Pre-order Routes

Endpoints:
    POST   /preorders/import-csv           – Import pre-orders from CSV file.
    GET    /preorders/                      – List pre-orders (paginated, filterable).
    GET    /preorders/lookup/{barcode_code} – Lookup pre-order by barcode (POS scanner).
    GET    /preorders/{preorder_id}         – Get a single pre-order.
    POST   /preorders/fulfill/{barcode_code}– Fulfill a pre-order (create real order).
    DELETE /preorders/{preorder_id}         – Cancel a pre-order (soft delete).
"""

import csv
import io
import math
import re
import random
import string
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from pymongo import ReturnDocument, UpdateOne

from auth import get_current_user, require_role
from config import settings
from database import get_collection
from middleware import log_action
from models import PaginatedResponse, PreOrderResponse, PreOrderCreate
from email_service import send_preorder_email

router = APIRouter(prefix="/preorders", tags=["PreOrders"])


@router.post("", response_model=PreOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_preorder(
    payload: PreOrderCreate,
    current_user: dict = Depends(require_role("admin", "manager"))
):
    """Create a single pre-order manually."""
    if not payload.items:
        raise HTTPException(status_code=400, detail="Đơn hàng phải có ít nhất 1 sản phẩm")

    products_col = get_collection("products")
    
    # Process items
    processed_items = []
    subtotal = 0.0
    
    for item in payload.items:
        product = await products_col.find_one({"_id": ObjectId(item.product_id)})
        if not product:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy sản phẩm có ID: {item.product_id}")
            
        line_total = product["price"] * item.quantity
        subtotal += line_total
        processed_items.append({
            "product_id": str(product["_id"]),
            "product_name": product["name"],
            "price": product["price"],
            "quantity": item.quantity
        })
        
    vat_rate = getattr(settings, "VAT_RATE", 0.0)
    vat_amount = subtotal * (vat_rate / 100)
    total = subtotal + vat_amount

    # Generate code
    barcode_code = await _generate_preorder_code()

    preorder_doc = {
        "barcode_code": barcode_code,
        "customer_name": payload.customer_name,
        "email": payload.email,
        "items": processed_items,
        "subtotal": subtotal,
        "vat_rate": vat_rate,
        "vat_amount": vat_amount,
        "total": total,
        "status": "pending",
        "created_by": current_user["username"],
        "created_at": datetime.now(timezone.utc),
    }

    preorders_col = get_collection("preorders")
    result = await preorders_col.insert_one(preorder_doc)
    preorder_doc["_id"] = result.inserted_id

    await log_action(
        user_id=str(current_user["_id"]),
        username=current_user["username"],
        action="CREATE_PREORDER",
        details=f"Tạo đơn đặt trước thủ công {barcode_code} cho {payload.customer_name}"
    )

    import asyncio
    asyncio.create_task(
        send_preorder_email(
            to_email=payload.email,
            customer_name=payload.customer_name,
            barcode_code=barcode_code,
            items=processed_items,
            subtotal=subtotal,
            vat_amount=vat_amount,
            total=total
        )
    )

    return PreOrderResponse.from_doc(preorder_doc)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

async def _generate_preorder_code() -> str:
    """Generate a unique pre-order barcode code: PRE-YYYYMMDD-XXXX with 4 random digits."""
    today_str = datetime.now().astimezone().strftime("%Y%m%d")
    prefix = f"PRE-{today_str}-"
    preorders_col = get_collection("preorders")
    
    for _ in range(10):
        suffix = "".join(random.choices(string.digits, k=4))
        code = f"{prefix}{suffix}"
        exists = await preorders_col.find_one({"barcode_code": code})
        if not exists:
            return code
            
    # Fallback in case of highly unlikely collisions
    suffix = "".join(random.choices(string.digits, k=6))
    return f"{prefix}{suffix}"


async def _generate_order_number() -> str:
    """Generate the next sequential order number for today."""
    today_str = datetime.now().astimezone().strftime("%Y%m%d")
    prefix = f"ORD-{today_str}-"
    counters = get_collection("counters")
    counter_doc = await counters.find_one_and_update(
        {"_id": f"order_number_{today_str}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return f"{prefix}{counter_doc['seq']:04d}"


# --------------------------------------------------------------------------
# Import CSV
# --------------------------------------------------------------------------

@router.post("/import-csv")
async def import_csv(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_role("admin", "manager")),
):
    """Upload a CSV file to create pre-orders and send barcode emails."""
    content = await file.read()
    # Decode with BOM handling (Excel/Google Sheets may add BOM)
    text = content.decode("utf-8-sig")

    reader = csv.DictReader(io.StringIO(text))
    required_cols = {"customer_name", "email", "product_name", "quantity"}
    if not reader.fieldnames or not required_cols.issubset(set(reader.fieldnames)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV thiếu cột bắt buộc. Cần có: {', '.join(sorted(required_cols))}",
        )

    products_col = get_collection("products")
    preorders_col = get_collection("preorders")

    # Group rows by email → each email = 1 pre-order
    groups: dict[str, dict] = {}
    row_num = 1
    for row in reader:
        row_num += 1
        email = row.get("email", "").strip().lower()
        if not email:
            continue
        if email not in groups:
            groups[email] = {
                "customer_name": row.get("customer_name", "").strip(),
                "items": [],
            }
        prod_name = row.get("product_name", "").strip()
        if not prod_name:
            continue
        try:
            qty = int(row.get("quantity", "0").strip())
            if qty > 0:
                groups[email]["items"].append({
                    "product_name": prod_name,
                    "quantity": qty,
                    "row": row_num,
                })
        except ValueError:
            pass

    success_count = 0
    errors: list[str] = []
    created_preorders = []

    for email, group in groups.items():
        items_to_save = []
        subtotal = 0.0

        for item in group["items"]:
            prod_name = item["product_name"]
            safe_name = re.escape(prod_name)

            # 1. Exact case-insensitive match
            product = await products_col.find_one(
                {"name": {"$regex": f"^{safe_name}$", "$options": "i"}}
            )
            # 2. Fallback to contains
            if not product:
                product = await products_col.find_one(
                    {"name": {"$regex": safe_name, "$options": "i"}}
                )

            if not product:
                errors.append(f"Dòng {item['row']}: Không tìm thấy sản phẩm '{prod_name}'")
                continue

            price = float(product.get("price", 0))
            qty = item["quantity"]
            subtotal += price * qty
            items_to_save.append({
                "product_id": str(product["_id"]),
                "product_name": product["name"],
                "price": price,
                "quantity": qty,
            })

        if not items_to_save:
            errors.append(f"Email {email}: Không có sản phẩm hợp lệ nào")
            continue

        vat_rate = settings.VAT_RATE
        vat_amount = round(subtotal * (vat_rate / 100), 2)
        total = round(subtotal + vat_amount, 2)

        barcode_code = await _generate_preorder_code()

        doc = {
            "barcode_code": barcode_code,
            "customer_name": group["customer_name"],
            "email": email,
            "items": items_to_save,
            "subtotal": round(subtotal, 2),
            "vat_rate": vat_rate,
            "vat_amount": vat_amount,
            "total": total,
            "status": "pending",
            "created_by": current_user.get("full_name", current_user["username"]),
            "created_at": datetime.now(timezone.utc),
            "fulfilled_at": None,
            "fulfilled_by": None,
            "order_id": None,
        }

        result = await preorders_col.insert_one(doc)
        doc["_id"] = result.inserted_id

        # Send email (non-blocking failure)
        try:
            await send_preorder_email(
                to_email=email,
                customer_name=group["customer_name"],
                barcode_code=barcode_code,
                items=items_to_save,
                subtotal=subtotal,
                vat_amount=vat_amount,
                total=total,
            )
        except Exception as e:
            print(f"[PREORDER] Email send failed for {email}: {e}")

        created_preorders.append(PreOrderResponse.from_doc(doc).model_dump())
        success_count += 1

    # Audit log
    await log_action(
        action="IMPORT_PREORDERS",
        user_id=str(current_user["_id"]),
        username=current_user["username"],
        details=f"Imported {success_count} pre-orders from CSV. Errors: {len(errors)}",
    )

    return {
        "success": success_count,
        "errors": errors,
        "preorders": created_preorders,
    }


# --------------------------------------------------------------------------
# List pre-orders
# --------------------------------------------------------------------------

@router.get("", response_model=PaginatedResponse)
async def list_preorders(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: dict = Depends(require_role("admin", "manager")),
):
    """Return a paginated list of pre-orders, optionally filtered by status."""
    col = get_collection("preorders")
    query: dict = {}
    if status_filter:
        query["status"] = status_filter

    total = await col.count_documents(query)
    skip = (page - 1) * per_page

    cursor = col.find(query).sort("created_at", -1).skip(skip).limit(per_page)
    docs = await cursor.to_list(length=per_page)

    items = [PreOrderResponse.from_doc(d).model_dump() for d in docs]
    return PaginatedResponse.build(items=items, total=total, page=page, per_page=per_page)


# --------------------------------------------------------------------------
# Lookup by barcode (POS scanner) — MUST be before /{preorder_id}
# --------------------------------------------------------------------------

@router.get("/lookup/{barcode_code}", response_model=PreOrderResponse)
async def lookup_preorder(
    barcode_code: str,
    current_user: dict = Depends(get_current_user),
):
    """Find a pre-order by its barcode code (used by POS scanner)."""
    col = get_collection("preorders")
    doc = await col.find_one({"barcode_code": barcode_code})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy đơn đặt trước với mã: {barcode_code}",
        )
    return PreOrderResponse.from_doc(doc)


# --------------------------------------------------------------------------
# Single pre-order by ID
# --------------------------------------------------------------------------

@router.get("/{preorder_id}", response_model=PreOrderResponse)
async def get_preorder(
    preorder_id: str,
    current_user: dict = Depends(require_role("admin", "manager")),
):
    """Return a single pre-order by its MongoDB _id."""
    try:
        oid = ObjectId(preorder_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pre-order ID format.",
        )

    col = get_collection("preorders")
    doc = await col.find_one({"_id": oid})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pre-order not found.",
        )
    return PreOrderResponse.from_doc(doc)


# --------------------------------------------------------------------------
# Fulfill pre-order (scan barcode → create real order)
# --------------------------------------------------------------------------

@router.post("/fulfill/{barcode_code}")
async def fulfill_preorder(
    barcode_code: str,
    current_user: dict = Depends(get_current_user),
):
    """Fulfill a pending pre-order: create a real order, deduct stock, update status."""
    col = get_collection("preorders")
    doc = await col.find_one({"barcode_code": barcode_code})

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy đơn đặt trước với mã: {barcode_code}",
        )

    if doc["status"] == "fulfilled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Đơn hàng đã được giao trước đó.",
        )
    if doc["status"] == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Đơn hàng đã bị huỷ.",
        )

    # Create a real order
    orders_col = get_collection("orders")
    products_col = get_collection("products")

    order_number = await _generate_order_number()
    now = datetime.now(timezone.utc)
    user_id = str(current_user["_id"])
    cashier_name = current_user.get("full_name", current_user["username"])

    order_doc = {
        "order_number": order_number,
        "items": doc["items"],
        "subtotal": doc["subtotal"],
        "vat_rate": doc["vat_rate"],
        "vat_amount": doc["vat_amount"],
        "total": doc["total"],
        "actual_revenue": doc["total"],
        "payment_method": "transfer",
        "payments": None,
        "amount_given": None,
        "expected_change": None,
        "actual_change": None,
        "cashier_id": user_id,
        "cashier_name": cashier_name,
        "created_at": now,
    }

    result = await orders_col.insert_one(order_doc)
    order_id = result.inserted_id

    # Deduct stock
    bulk_ops = []
    for item in doc["items"]:
        try:
            pid = ObjectId(item["product_id"])
            bulk_ops.append(
                UpdateOne({"_id": pid}, {"$inc": {"stock": -item["quantity"]}})
            )
        except Exception:
            pass
    if bulk_ops:
        try:
            await products_col.bulk_write(bulk_ops)
        except Exception:
            pass

    # Update pre-order status
    updated_doc = await col.find_one_and_update(
        {"_id": doc["_id"]},
        {
            "$set": {
                "status": "fulfilled",
                "fulfilled_at": now,
                "fulfilled_by": cashier_name,
                "order_id": str(order_id),
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    # Audit log
    await log_action(
        action="FULFILL_PREORDER",
        user_id=user_id,
        username=current_user["username"],
        details=f"Fulfilled pre-order {barcode_code} → order {order_number}",
    )

    return PreOrderResponse.from_doc(updated_doc)


# --------------------------------------------------------------------------
# Cancel pre-order (soft delete)
# --------------------------------------------------------------------------

@router.delete("/{preorder_id}")
async def cancel_preorder(
    preorder_id: str,
    current_user: dict = Depends(require_role("admin", "manager")),
):
    """Cancel a pre-order (soft delete — sets status to 'cancelled')."""
    try:
        oid = ObjectId(preorder_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pre-order ID format.",
        )

    col = get_collection("preorders")
    doc = await col.find_one_and_update(
        {"_id": oid, "status": "pending"},
        {"$set": {"status": "cancelled"}},
        return_document=ReturnDocument.AFTER,
    )

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Đơn đặt trước không tồn tại hoặc không thể huỷ.",
        )

    # Audit log
    await log_action(
        action="CANCEL_PREORDER",
        user_id=str(current_user["_id"]),
        username=current_user["username"],
        details=f"Cancelled pre-order {doc.get('barcode_code', preorder_id)}",
    )

    return {"message": "Đã huỷ đơn đặt trước."}
