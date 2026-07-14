"""
EViENT POS - System Logs Routes

Endpoints:
    GET /logs/ - List system logs (paginated, admin only).
"""

from fastapi import APIRouter, Depends, Query
from auth import require_role
from database import get_collection
from models import PaginatedResponse, SystemLogResponse

router = APIRouter(prefix="/logs", tags=["Logs"])


@router.get("", response_model=PaginatedResponse)
async def list_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(require_role("admin")),
):
    """Return a paginated list of system logs.
    
    Requires the ``admin`` role.
    """
    logs = get_collection("system_logs")
    total = await logs.count_documents({})
    skip = (page - 1) * per_page

    cursor = (
        logs.find({})
        .sort("timestamp", -1)
        .skip(skip)
        .limit(per_page)
    )
    docs = await cursor.to_list(length=per_page)

    # Convert the raw documents into the SystemLogResponse schema
    items = []
    for d in docs:
        items.append(SystemLogResponse.from_doc(d).model_dump())

    return PaginatedResponse.build(items=items, total=total, page=page, per_page=per_page)
