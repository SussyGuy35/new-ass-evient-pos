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
from fastapi import APIRouter, Depends, HTTPException, status
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
    try:
        if not is_online():
            raise Exception("MongoDB is offline (fast fallback)")
            
        async def fetch_remote():
            categories_col = get_collection("categories")
            return await categories_col.find({}).sort("name", 1).to_list(None)
            
        docs = await asyncio.wait_for(fetch_remote(), timeout=2.0)
        return [CategoryResponse.from_doc(d) for d in docs]
    except Exception as e:
        from database import mark_offline
        mark_offline()
        print(f"[CATEGORY] Network error reading categories: {e}. Falling back to local cache.")
        cached = await local_db.get_cached_categories()
        # Convert _id to id if necessary, though cache returns 'id' already
        for c in cached:
            if "id" in c and "_id" not in c:
                c["_id"] = c["id"]
        return [CategoryResponse.from_doc(c) for c in cached]


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
    
    return CategoryResponse.from_doc(doc)


@router.put("/{cat_id}", response_model=CategoryResponse)
async def update_category(
    cat_id: str,
    payload: CategoryUpdate,
    current_user: dict = Depends(require_role("admin", "manager")),
):
    """Update a category."""
    if not ObjectId.is_valid(cat_id):
        raise HTTPException(status_code=400, detail="ID không hợp lệ")

    categories_col = get_collection("categories")
    
    update_data = {}
    if payload.name is not None:
        update_data["name"] = payload.name
        
    if not update_data:
        raise HTTPException(status_code=400, detail="Không có dữ liệu cập nhật")
        
    update_data["updated_at"] = datetime.now(timezone.utc)
    
    updated_doc = await categories_col.find_one_and_update(
        {"_id": ObjectId(cat_id)},
        {"$set": update_data},
        return_document=ReturnDocument.AFTER,
    )
    
    if not updated_doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy danh mục")
        
    await log_action(
        action="UPDATE_CATEGORY",
        user_id=str(current_user["_id"]),
        username=current_user["username"],
        details=f"Updated category: {updated_doc['name']}"
    )
    
    return CategoryResponse.from_doc(updated_doc)


@router.delete("/{cat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    cat_id: str,
    current_user: dict = Depends(require_role("admin", "manager")),
):
    """Delete a category."""
    if not ObjectId.is_valid(cat_id):
        raise HTTPException(status_code=400, detail="ID không hợp lệ")

    categories_col = get_collection("categories")
    doc = await categories_col.find_one({"_id": ObjectId(cat_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy danh mục")
        
    await categories_col.delete_one({"_id": ObjectId(cat_id)})
    
    await log_action(
        action="DELETE_CATEGORY",
        user_id=str(current_user["_id"]),
        username=current_user["username"],
        details=f"Deleted category: {doc['name']}"
    )
    
    return None
