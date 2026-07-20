"""
EViENT POS - Product Routes

Endpoints:
    GET    /products/               – List/search products (paginated).
    GET    /products/barcode/{bc}   – Find product by exact barcode.
    GET    /products/{id}           – Get a single product.
    POST   /products/               – Create a product (admin/manager).
    PUT    /products/{id}           – Update a product (admin/manager).
    DELETE /products/{id}           – Delete a product (admin/manager).
"""

from datetime import datetime, timezone
import re

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from auth import get_current_user, require_role
from database import get_collection
from middleware import log_action
from models import (
    PaginatedResponse,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
)

router = APIRouter(prefix="/products", tags=["Products"])


# --------------------------------------------------------------------------
# List / Search
# --------------------------------------------------------------------------

@router.get("", response_model=PaginatedResponse)
async def list_products(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    q: str = Query(None, description="Search by name or barcode"),
    current_user: dict = Depends(get_current_user),
):
    """Return a paginated (and optionally filtered) list of products.

    The ``q`` query parameter performs a case-insensitive search against
    the product name **or** barcode.
    Falls back to local SQLite cache if MongoDB is unreachable.
    """
    try:
        products = get_collection("products")

        query_filter: dict = {}
        if q:
            safe_q = re.escape(q)
            query_filter = {
                "$or": [
                    {"name": {"$regex": safe_q, "$options": "i"}},
                    {"barcode": {"$regex": safe_q, "$options": "i"}},
                ]
            }

        total = await products.count_documents(query_filter)
        skip = (page - 1) * per_page

        cursor = (
            products.find(query_filter)
            .sort("created_at", -1)
            .skip(skip)
            .limit(per_page)
        )
        docs = await cursor.to_list(length=per_page)

        items = [ProductResponse.from_doc(d).model_dump() for d in docs]
        return PaginatedResponse.build(items=items, total=total, page=page, per_page=per_page)
    except Exception:
        # Offline fallback → read from SQLite cache
        import local_db
        cached_items, total = await local_db.get_cached_products(page, per_page, q)
        return PaginatedResponse.build(items=cached_items, total=total, page=page, per_page=per_page)


# --------------------------------------------------------------------------
# Barcode lookup
# --------------------------------------------------------------------------

@router.get("/barcode/{barcode}", response_model=ProductResponse)
async def get_product_by_barcode(
    barcode: str,
    current_user: dict = Depends(get_current_user),
):
    """Find a single product by its exact barcode."""
    doc = None
    try:
        products = get_collection("products")
        doc = await products.find_one({"barcode": barcode})
    except Exception:
        pass  # Offline – try cache below

    if doc is None:
        # Offline fallback
        import local_db
        cached = await local_db.get_cached_product_by_barcode(barcode)
        if cached:
            return cached
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with barcode '{barcode}' not found.",
        )

    return ProductResponse.from_doc(doc)


# --------------------------------------------------------------------------
# Single product
# --------------------------------------------------------------------------

@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return a single product by its ID."""
    products = get_collection("products")

    try:
        oid = ObjectId(product_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid product ID format.",
        )

    doc = await products.find_one({"_id": oid})
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        )

    return ProductResponse.from_doc(doc)


# --------------------------------------------------------------------------
# Create
# --------------------------------------------------------------------------

@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    body: ProductCreate,
    request: Request,
    current_user: dict = Depends(require_role("admin", "manager")),
):
    """Create a new product.

    Requires ``admin`` or ``manager`` role. Duplicate barcodes are rejected
    when the barcode field is provided.
    """
    products = get_collection("products")

    # Check barcode uniqueness
    if body.barcode:
        existing = await products.find_one({"barcode": body.barcode})
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Barcode '{body.barcode}' already exists.",
            )

    doc = {
        "name": body.name,
        "barcode": body.barcode,
        "price": body.price,
        "category": body.category,
        "stock": body.stock,
        "image_url": body.image_url,
        "created_at": datetime.now(timezone.utc),
    }
    result = await products.insert_one(doc)
    doc["_id"] = result.inserted_id

    # Audit log
    client_ip = request.client.host if request.client else ""
    await log_action(
        action="CREATE_PRODUCT",
        user_id=str(current_user["_id"]),
        username=current_user["username"],
        details=f"Created product '{body.name}' (barcode: {body.barcode}).",
        ip_address=client_ip,
    )

    return ProductResponse.from_doc(doc)


# --------------------------------------------------------------------------
# Update
# --------------------------------------------------------------------------

@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str,
    body: ProductUpdate,
    request: Request,
    current_user: dict = Depends(require_role("admin", "manager")),
):
    """Update an existing product.

    Requires ``admin`` or ``manager`` role.
    """
    products = get_collection("products")

    try:
        oid = ObjectId(product_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid product ID format.",
        )

    update_data = {k: v for k, v in body.model_dump().items() if v is not None}

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update.",
        )

    # Barcode uniqueness if changed
    if "barcode" in update_data and update_data["barcode"]:
        dup = await products.find_one(
            {"barcode": update_data["barcode"], "_id": {"$ne": oid}}
        )
        if dup:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Barcode '{update_data['barcode']}' already in use.",
            )

    result = await products.find_one_and_update(
        {"_id": oid},
        {"$set": update_data},
        return_document=True,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        )

    # Audit log
    client_ip = request.client.host if request.client else ""
    await log_action(
        action="UPDATE_PRODUCT",
        user_id=str(current_user["_id"]),
        username=current_user["username"],
        details=f"Updated product '{product_id}'. Fields: {list(update_data.keys())}.",
        ip_address=client_ip,
    )

    return ProductResponse.from_doc(result)


# --------------------------------------------------------------------------
# Delete
# --------------------------------------------------------------------------

@router.delete("/{product_id}", status_code=status.HTTP_200_OK)
async def delete_product(
    product_id: str,
    request: Request,
    current_user: dict = Depends(require_role("admin", "manager")),
):
    """Delete a product by its ID.

    Requires ``admin`` or ``manager`` role.
    """
    products = get_collection("products")

    try:
        oid = ObjectId(product_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid product ID format.",
        )

    result = await products.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        )

    # Audit log
    client_ip = request.client.host if request.client else ""
    await log_action(
        action="DELETE_PRODUCT",
        user_id=str(current_user["_id"]),
        username=current_user["username"],
        details=f"Deleted product '{product_id}'.",
        ip_address=client_ip,
    )

    return {"message": "Product deleted successfully."}
