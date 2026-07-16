"""
EViENT POS - Drawer Routes

Endpoints:
    GET  /drawer              - Get current drawer balance
    GET  /drawer/transactions - List drawer transactions (paginated)
    POST /drawer/transaction  - Add a manual transaction (pay_in/pay_out)
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pymongo import ReturnDocument

from auth import get_current_user, require_role
from database import get_collection
from middleware import log_action
from models import (
    DrawerStateResponse,
    DrawerTransactionCreate,
    DrawerTransactionResponse,
    PaginatedResponse,
)

router = APIRouter(prefix="/drawer", tags=["Drawer"])


@router.get("", response_model=DrawerStateResponse)
async def get_drawer_balance(current_user: dict = Depends(get_current_user)):
    """Get the current cash drawer balance."""
    drawer_state = get_collection("drawer_state")
    doc = await drawer_state.find_one({"_id": "main_drawer"})
    
    if not doc:
        # Initialize if not exists
        doc = {
            "_id": "main_drawer",
            "balance": 0.0,
            "last_updated": datetime.now(timezone.utc)
        }
        await drawer_state.insert_one(doc)
        
    return DrawerStateResponse(
        balance=doc["balance"],
        last_updated=doc["last_updated"]
    )


@router.get("/transactions", response_model=PaginatedResponse)
async def list_transactions(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """List paginated drawer transactions."""
    transactions = get_collection("drawer_transactions")
    total = await transactions.count_documents({})
    skip = (page - 1) * per_page

    cursor = (
        transactions.find({})
        .sort("created_at", -1)
        .skip(skip)
        .limit(per_page)
    )
    docs = await cursor.to_list(length=per_page)

    items = [DrawerTransactionResponse.from_doc(d).model_dump() for d in docs]
    return PaginatedResponse.build(items=items, total=total, page=page, per_page=per_page)


@router.post("/transaction", response_model=DrawerTransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    body: DrawerTransactionCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Create a manual drawer transaction (pay_in or pay_out)."""
    
    if body.type not in ["pay_in", "pay_out"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pay_in or pay_out allowed for manual transactions."
        )
        
    if body.type == "pay_out" and body.amount > 0:
        # Ensure pay_out amount is negative for consistency, or subtract it
        # Actually we expect user to pass positive amount and we negate it for pay_out
        amount = -body.amount
    else:
        amount = body.amount
        
    # Double check so pay_out is negative, pay_in is positive
    if body.type == "pay_in" and amount < 0:
        amount = -amount

    now = datetime.now(timezone.utc)
    
    # 1. Update global drawer state
    drawer_state = get_collection("drawer_state")
    updated_state = await drawer_state.find_one_and_update(
        {"_id": "main_drawer"},
        {
            "$inc": {"balance": amount},
            "$set": {"last_updated": now}
        },
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    
    # 2. Record transaction
    doc = {
        "amount": amount,
        "type": body.type,
        "note": body.note,
        "user_id": str(current_user["_id"]),
        "username": current_user["username"],
        "created_at": now
    }
    transactions = get_collection("drawer_transactions")
    result = await transactions.insert_one(doc)
    doc["_id"] = result.inserted_id
    
    # 3. Log audit action
    client_ip = request.client.host if request.client else ""
    await log_action(
        action=f"DRAWER_{body.type.upper()}",
        user_id=str(current_user["_id"]),
        username=current_user["username"],
        details=f"Amount: {amount:,.0f} | Note: {body.note}",
        ip_address=client_ip
    )
    
    return DrawerTransactionResponse.from_doc(doc)
