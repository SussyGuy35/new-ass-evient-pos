"""
EViENT POS - Category Routes

Endpoints:
    GET    /categories/       – List all categories
    POST   /categories/       – Create a new category
    PUT    /categories/{id}   – Update a category
    DELETE /categories/{id}   – Delete a category
"""

from datetime import datetime, timezone
import asyncio

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pymongo import ReturnDocument

from auth import get_current_user, require_role
from database import get_collection, is_online
from middleware import log_action
from models import CategoryCreate, CategoryUpdate, CategoryResponse

router = APIRouter(prefix="/categories", tags=["Categories"])

import local_db

@router.get("", response_model=list[CategoryResponse])
async def list_categories():
    """List all product categories, ordered by 'order'. Fallback to local_db if offline."""
    import local_db
    cached = await local_db.get_cached_categories()
    for c in cached:
        c["id"] = c.get("_id", c.get("id"))
    return [CategoryResponse(**c) for c in cached]


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    current_user: dict = Depends(require_role("admin", "manager")),
):
    """Create a new category."""
    categories_col = get_collection("categories")
    
    # Check if category with the same name exists
    existing = await categories_col.find_one({"name": payload.name})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Tên danh mục đã tồn tại"
        )
        
    doc = {
        "name": payload.name,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    
    result = await categories_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    
    await log_action(
        action="CREATE_CATEGORY",
        user_id=str(current_user["_id"]),
        username=current_user["username"],
        details=f"Created category: {payload.name}"
    )
    
    import local_db
    await local_db.save_single_category(doc)
    return CategoryResponse.from_doc(doc)

@router.put("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: str,
    body: CategoryUpdate,
    request: Request,
    current_user: dict = Depends(require_role("admin", "manager")),
):
    """Update a category."""
    categories = get_collection("categories")
    
    try:
        oid = ObjectId(category_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid category ID format.",
        )

    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update.",
        )

    # Check for name duplication if changing name
    if "name" in update_data and update_data["name"]:
        dup = await categories.find_one({"name": update_data["name"], "_id": {"$ne": oid}})
        if dup:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Category '{update_data['name']}' already exists.",
            )

    update_data["updated_at"] = datetime.now(timezone.utc)
    result = await categories.find_one_and_update(
        {"_id": oid},
        {"$set": update_data},
        return_document=True
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found.",
        )

    # Audit log
    client_ip = request.client.host if request.client else ""
    await log_action(
        action="UPDATE_CATEGORY",
        user_id=str(current_user["_id"]),
        username=current_user["username"],
        details=f"Updated category '{category_id}'. Fields: {list(update_data.keys())}.",
        ip_address=client_ip,
    )

    import local_db
    await local_db.save_single_category(result)
    return CategoryResponse.from_doc(result)

@router.delete("/{category_id}", status_code=status.HTTP_200_OK)
async def delete_category(
    category_id: str,
    request: Request,
    current_user: dict = Depends(require_role("admin", "manager")),
):
    """Delete a category."""
    categories = get_collection("categories")
    try:
        oid = ObjectId(category_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid category ID format.",
        )

    result = await categories.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found.",
        )

    # Audit log
    client_ip = request.client.host if request.client else ""
    await log_action(
        action="DELETE_CATEGORY",
        user_id=str(current_user["_id"]),
        username=current_user["username"],
        details=f"Deleted category '{category_id}'.",
        ip_address=client_ip,
    )

    import local_db
    await local_db.delete_cached_category(category_id)
    return {"message": "Category deleted successfully"}
