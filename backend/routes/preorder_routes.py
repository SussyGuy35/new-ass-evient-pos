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
from models import PaginatedResponse, PreOrderResponse, PreOrderCreate, PreOrderConfirmBatch
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
            
        actual_price = float(product.get("preorder_price") if product.get("preorder_price") is not None else product.get("price", 0))
        line_total = actual_price * item.quantity
        subtotal += line_total
        processed_items.append({
            "product_id": str(product["_id"]),
            "product_name": product["name"],
            "price": actual_price,
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
        "note": payload.note,
        "created_by": current_user["username"],
        "created_at": datetime.now(timezone.utc),
    }

    preorders_col = get_collection("preorders")
    result = await preorders_col.insert_one(preorder_doc)
    preorder_doc["_id"] = result.inserted_id

    # Reserve stock
    from pymongo import UpdateOne
    bulk_ops = []
    for item in processed_items:
        try:
            pid = ObjectId(item["product_id"])
            bulk_ops.append(
                UpdateOne({"_id": pid}, {"$inc": {"stock_reserved": item["quantity"]}})
            )
        except Exception:
            pass
    if bulk_ops:
        await products_col.bulk_write(bulk_ops)

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

@router.post("/preview-csv")
async def preview_csv(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_role("admin", "manager")),
):
    """Upload a CSV file to parse and validate pre-orders, returning a preview."""
    content = await file.read()
    # Decode with BOM handling (Excel/Google Sheets may add BOM)
    text = content.decode("utf-8-sig")

    reader = csv.DictReader(io.StringIO(text))
    required_cols = {"customer_name", "email", "quantity"}
    if not reader.fieldnames or not required_cols.issubset(set(reader.fieldnames)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV thiếu cột bắt buộc. Cần có: {', '.join(sorted(required_cols))}, và (product_name hoặc barcode)",
        )
    if "product_name" not in reader.fieldnames and "barcode" not in reader.fieldnames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV phải có ít nhất một trong hai cột 'product_name' hoặc 'barcode'",
        )

    products_col = get_collection("products")

    # Group rows by email → each email = 1 pre-order
    groups: dict[str, dict] = {}
    row_num = 1
    for row in reader:
        row_num += 1
        email = row.get("email", "").strip().lower()
        if not email:
            continue
        note = row.get("note", "").strip()
        if email not in groups:
            groups[email] = {
                "customer_name": row.get("customer_name", "").strip(),
                "note": note,
                "items": [],
            }
        else:
            if note and note not in groups[email]["note"]:
                if groups[email]["note"]:
                    groups[email]["note"] += f" | {note}"
                else:
                    groups[email]["note"] = note
        
        prod_name = row.get("product_name", "").strip() if "product_name" in row else ""
        barcode = row.get("barcode", "").strip() if "barcode" in row else ""
        
        if not prod_name and not barcode:
            continue
            
        try:
            qty = int(row.get("quantity", "0").strip())
            if qty > 0:
                groups[email]["items"].append({
                    "product_name": prod_name,
                    "barcode": barcode,
                    "quantity": qty,
                    "row": row_num,
                })
        except ValueError:
            pass

    errors: list[str] = []
    valid_preorders = []

    for email, group in groups.items():
        items_to_save = []
        subtotal = 0.0

        for item in group["items"]:
            prod_name = item["product_name"]
            barcode = item.get("barcode", "")
            
            product = None
            
            # 1. Exact barcode match if barcode provided
            if barcode:
                product = await products_col.find_one({"barcode": barcode})
                
            # 2. Exact case-insensitive name match if name provided
            if not product and prod_name:
                safe_name = re.escape(prod_name)
                product = await products_col.find_one(
                    {"name": {"$regex": f"^{safe_name}$", "$options": "i"}}
                )
                # 3. Fallback to contains name
                if not product:
                    product = await products_col.find_one(
                        {"name": {"$regex": safe_name, "$options": "i"}}
                    )

            if not product:
                identifier = f"mã vạch '{barcode}'" if barcode else f"tên '{prod_name}'"
                errors.append(f"Dòng {item['row']}: Không tìm thấy sản phẩm {identifier}")
                continue

            price = float(product.get("preorder_price") if product.get("preorder_price") is not None else product.get("price", 0))
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

        valid_preorders.append({
            "customer_name": group["customer_name"],
            "email": email,
            "note": group.get("note", ""),
            "items": items_to_save,
            "subtotal": round(subtotal, 2),
            "vat_rate": vat_rate,
            "vat_amount": vat_amount,
            "total": total,
        })

    return {
        "valid_preorders": valid_preorders,
        "errors": errors,
    }


@router.post("/confirm-csv")
async def confirm_csv(
    payload: PreOrderConfirmBatch,
    current_user: dict = Depends(require_role("admin", "manager")),
):
    """Confirm and import the validated pre-orders from the preview step."""
    preorders_col = get_collection("preorders")
    products_col = get_collection("products")
    
    success_count = 0
    created_preorders = []

    for pre in payload.valid_preorders:
        barcode_code = await _generate_preorder_code()

        doc = {
            "barcode_code": barcode_code,
            "customer_name": pre.customer_name,
            "email": pre.email,
            "items": [item.model_dump() for item in pre.items],
            "subtotal": pre.subtotal,
            "vat_rate": pre.vat_rate,
            "vat_amount": pre.vat_amount,
            "total": pre.total,
            "status": "pending",
            "note": pre.note,
            "created_by": current_user.get("full_name", current_user["username"]),
            "created_at": datetime.now(timezone.utc),
            "fulfilled_at": None,
            "fulfilled_by": None,
            "order_id": None,
        }

        result = await preorders_col.insert_one(doc)
        doc["_id"] = result.inserted_id

        # Reserve stock
        bulk_ops = []
        for item in pre.items:
            try:
                pid = ObjectId(item.product_id)
                bulk_ops.append(
                    UpdateOne({"_id": pid}, {"$inc": {"stock_reserved": item.quantity}})
                )
            except Exception:
                pass
        if bulk_ops:
            await products_col.bulk_write(bulk_ops)

        # Send email (non-blocking failure)
        try:
            await send_preorder_email(
                to_email=pre.email,
                customer_name=pre.customer_name,
                barcode_code=barcode_code,
                items=[item.model_dump() for item in pre.items],
                subtotal=pre.subtotal,
                vat_amount=pre.vat_amount,
                total=pre.total,
            )
        except Exception as e:
            print(f"[PREORDER] Email send failed for {pre.email}: {e}")

        created_preorders.append(PreOrderResponse.from_doc(doc).model_dump())
        success_count += 1

    # Audit log
    await log_action(
        action="IMPORT_PREORDERS",
        user_id=str(current_user["_id"]),
        username=current_user["username"],
        details=f"Confirmed and imported {success_count} pre-orders.",
    )

    return {
        "success": success_count,
        "preorders": created_preorders,
    }



# --------------------------------------------------------------------------
# Bulk resend pre-order emails
# --------------------------------------------------------------------------

@router.post("/bulk-resend-email")
async def bulk_resend_preorder_email(
    payload: dict,
    current_user: dict = Depends(require_role("admin", "manager")),
):
    """Resend email notifications for multiple pre-orders."""
    ids = payload.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="Danh sách đơn hàng trống.")

    col = get_collection("preorders")
    success = 0
    failed = 0

    for preorder_id in ids:
        try:
            oid = ObjectId(preorder_id)
            doc = await col.find_one({"_id": oid})
            if not doc:
                failed += 1
                continue

            result = await send_preorder_email(
                to_email=doc["email"],
                customer_name=doc["customer_name"],
                barcode_code=doc["barcode_code"],
                items=doc.get("items", []),
                subtotal=doc.get("subtotal", 0.0),
                vat_amount=doc.get("vat_amount", 0.0),
                total=doc.get("total", 0.0),
            )
            if result:
                success += 1
            else:
                failed += 1
        except Exception:
            failed += 1

    # Audit log
    await log_action(
        action="BULK_RESEND_PREORDER_EMAIL",
        user_id=str(current_user["_id"]),
        username=current_user["username"],
        details=f"Bulk resent emails: {success} success, {failed} failed, total {len(ids)}",
    )

    return {
        "message": f"Đã gửi {success}/{len(ids)} email thành công.",
        "success": success,
        "failed": failed,
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
    try:
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
    except Exception:
        # Offline fallback → read from SQLite cache
        import local_db
        cached_items, total = await local_db.get_cached_preorders(page, per_page, status_filter)
        items = [PreOrderResponse.from_doc(d).model_dump() for d in cached_items]
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
    try:
        col = get_collection("preorders")
        doc = await col.find_one({"barcode_code": barcode_code})
    except Exception:
        doc = None

    if doc is None:
        # Offline fallback → try SQLite cache
        try:
            import local_db
            cached = await local_db.get_cached_preorder_by_barcode(barcode_code)
            if cached:
                return PreOrderResponse.from_doc(cached)
        except Exception:
            pass
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

    try:
        col = get_collection("preorders")
        doc = await col.find_one({"_id": oid})
    except Exception:
        doc = None

    if doc is None:
        # Offline fallback → try SQLite cache
        try:
            import local_db
            cached = await local_db.get_cached_preorder_by_id(preorder_id)
            if cached:
                return PreOrderResponse.from_doc(cached)
        except Exception:
            pass
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
    import local_db

    is_offline = False
    doc = None

    # 1. Look up the preorder
    try:
        col = get_collection("preorders")
        doc = await col.find_one({"barcode_code": barcode_code})
    except Exception:
        is_offline = True

    if doc is None and not is_offline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy đơn đặt trước với mã: {barcode_code}",
        )

    if doc is None:
        # Offline fallback — look up from SQLite cache
        cached = await local_db.get_cached_preorder_by_barcode(barcode_code)
        if not cached:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không tìm thấy đơn đặt trước với mã: {barcode_code}",
            )
        doc = cached

    # 2. Validate status
    if doc.get("status") == "fulfilled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Đơn hàng đã được giao trước đó.",
        )
    if doc.get("status") == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Đơn hàng đã bị huỷ.",
        )

    # 3. Build order document
    now = datetime.now(timezone.utc)
    user_id = str(current_user["_id"])
    cashier_name = current_user.get("full_name", current_user["username"])
    preorder_id = str(doc.get("_id", doc.get("id", "")))

    # Generate order number
    try:
        order_number = await _generate_order_number()
    except Exception:
        is_offline = True
        order_number = await local_db.next_offline_order_number()

    order_doc = {
        "order_number": order_number,
        "items": doc["items"],
        "subtotal": doc["subtotal"],
        "vat_rate": doc["vat_rate"],
        "vat_amount": doc["vat_amount"],
        "total": doc["total"],
        "actual_revenue": doc["total"],
        "payment_method": "preorder",
        "payments": None,
        "amount_given": None,
        "expected_change": None,
        "actual_change": None,
        "cashier_id": user_id,
        "cashier_name": cashier_name,
        "created_at": now,
    }

    if is_offline:
        # --- OFFLINE PATH ---
        order_doc["_id"] = ObjectId()

        # Queue the order
        await local_db.queue_order(order_doc)

        # Queue the fulfill action for later sync to MongoDB
        await local_db.queue_preorder_fulfill({
            "preorder_id": preorder_id,
            "barcode_code": barcode_code,
            "order_doc": order_doc,
            "fulfilled_at": now.isoformat(),
            "fulfilled_by": cashier_name,
        })

        # Update local caches
        await local_db.update_cached_preorder_status(
            preorder_id, "fulfilled",
            fulfilled_at=now.isoformat(),
            fulfilled_by=cashier_name,
            order_id=str(order_doc["_id"]),
        )
        for item in doc["items"]:
            await local_db.deduct_cached_stock(
                item["product_id"], item["quantity"], item["quantity"]
            )

        # Build response
        doc["status"] = "fulfilled"
        doc["fulfilled_at"] = now
        doc["fulfilled_by"] = cashier_name
        doc["order_id"] = str(order_doc["_id"])
        if "_id" not in doc:
            doc["_id"] = preorder_id
    else:
        # --- ONLINE PATH ---
        try:
            orders_col = get_collection("orders")
            products_col = get_collection("products")

            result = await orders_col.insert_one(order_doc)
            order_id = result.inserted_id

            # Deduct stock and release reserved stock
            bulk_ops = []
            for item in doc["items"]:
                try:
                    pid = ObjectId(item["product_id"])
                    bulk_ops.append(
                        UpdateOne({"_id": pid}, {"$inc": {"stock": -item["quantity"], "stock_reserved": -item["quantity"]}})
                    )
                except Exception:
                    pass
            if bulk_ops:
                try:
                    await products_col.bulk_write(bulk_ops)
                except Exception:
                    pass

            # Also update local SQLite cache immediately
            try:
                for item in doc["items"]:
                    await local_db.deduct_cached_stock(item["product_id"], item["quantity"], item["quantity"])
            except Exception:
                pass

            # Update pre-order status
            doc = await col.find_one_and_update(
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

            # Update local preorder cache too
            try:
                await local_db.update_cached_preorder_status(
                    preorder_id, "fulfilled",
                    fulfilled_at=now.isoformat(),
                    fulfilled_by=cashier_name,
                    order_id=str(order_id),
                )
            except Exception:
                pass

        except Exception as exc:
            # MongoDB failed mid-operation — fall back to offline buffering
            print(f"[OFFLINE] Fulfill failed during write, buffering. {exc}")
            order_doc["_id"] = ObjectId()
            await local_db.queue_order(order_doc)
            await local_db.queue_preorder_fulfill({
                "preorder_id": preorder_id,
                "barcode_code": barcode_code,
                "order_doc": order_doc,
                "fulfilled_at": now.isoformat(),
                "fulfilled_by": cashier_name,
            })
            await local_db.update_cached_preorder_status(
                preorder_id, "fulfilled",
                fulfilled_at=now.isoformat(),
                fulfilled_by=cashier_name,
                order_id=str(order_doc["_id"]),
            )
            for item in doc["items"]:
                await local_db.deduct_cached_stock(
                    item["product_id"], item["quantity"], item["quantity"]
                )
            doc["status"] = "fulfilled"
            doc["fulfilled_at"] = now
            doc["fulfilled_by"] = cashier_name
            doc["order_id"] = str(order_doc["_id"])
            is_offline = True

    # Audit log
    await log_action(
        action="FULFILL_PREORDER",
        user_id=user_id,
        username=current_user["username"],
        details=f"Fulfilled pre-order {barcode_code} → order {order_number}" + (" [OFFLINE]" if is_offline else ""),
    )

    return PreOrderResponse.from_doc(doc)


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

    # Release reserved stock
    products_col = get_collection("products")
    bulk_ops = []
    for item in doc.get("items", []):
        try:
            pid = ObjectId(item["product_id"])
            bulk_ops.append(
                UpdateOne({"_id": pid}, {"$inc": {"stock_reserved": -item["quantity"]}})
            )
        except Exception:
            pass
    if bulk_ops:
        try:
            await products_col.bulk_write(bulk_ops)
        except Exception:
            pass

    # Audit log
    await log_action(
        action="CANCEL_PREORDER",
        user_id=str(current_user["_id"]),
        username=current_user["username"],
        details=f"Cancelled pre-order {doc.get('barcode_code', preorder_id)}",
    )

    return {"message": "Đã huỷ đơn đặt trước."}


# --------------------------------------------------------------------------
# Resend pre-order email
# --------------------------------------------------------------------------

@router.post("/{preorder_id}/resend-email")
async def resend_preorder_email(
    preorder_id: str,
    current_user: dict = Depends(require_role("admin", "manager")),
):
    """Resend email notification for a pre-order."""
    try:
        oid = ObjectId(preorder_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mã đơn hàng không hợp lệ.",
        )

    col = get_collection("preorders")
    doc = await col.find_one({"_id": oid})

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy đơn đặt trước.",
        )

    success = await send_preorder_email(
        to_email=doc["email"],
        customer_name=doc["customer_name"],
        barcode_code=doc["barcode_code"],
        items=doc.get("items", []),
        subtotal=doc.get("subtotal", 0.0),
        vat_amount=doc.get("vat_amount", 0.0),
        total=doc.get("total", 0.0),
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Gửi email thất bại. Vui lòng kiểm tra cấu hình SMTP.",
        )

    # Audit log
    await log_action(
        action="RESEND_PREORDER_EMAIL",
        user_id=str(current_user["_id"]),
        username=current_user["username"],
        details=f"Resent email for pre-order {doc.get('barcode_code', preorder_id)} to {doc.get('email')}",
    )

    return {"message": "Đã gửi lại email thành công."}

