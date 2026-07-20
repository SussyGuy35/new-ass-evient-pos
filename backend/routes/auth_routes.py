"""
EViENT POS - Authentication & User Management Routes

Endpoints:
    POST   /auth/login        – Authenticate and receive a JWT.
    GET    /auth/me            – Get current user profile.
    GET    /auth/users         – List all users (admin only).
    POST   /auth/users         – Create a new user (admin only).
    PUT    /auth/users/{id}    – Update a user (admin only).
    DELETE /auth/users/{id}    – Delete a user (admin only).
"""

from datetime import datetime, timezone
import re

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from auth import (
    create_access_token,
    get_current_user,
    hash_password,
    require_role,
    verify_password,
)
from database import get_collection
from middleware import log_action
from models import (
    PaginatedResponse,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
    UserUpdate,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# --------------------------------------------------------------------------
# Login
# --------------------------------------------------------------------------

@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, request: Request):
    """Authenticate a user and return a JWT access token.

    Verifies the username/password combination against the database,
    creates a signed JWT, logs the action, and returns the token along
    with the user profile.
    Falls back to local SQLite cache if MongoDB is unreachable.
    """
    user = None
    is_offline = False

    try:
        users = get_collection("users")
        user = await users.find_one({"username": body.username})
    except Exception:
        # MongoDB is down – try local cache
        is_offline = True

    if is_offline or user is None:
        # Attempt offline login from SQLite cache
        import local_db
        cached = await local_db.get_cached_user_by_username(body.username)
        if cached and verify_password(body.password, cached["password"]):
            user = cached
            is_offline = True
        elif cached is None and not is_offline:
            # MongoDB was reachable but user not found
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password.",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password.",
            )
    elif not verify_password(body.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    token = create_access_token(
        {
            "user_id": str(user["_id"]),
            "username": user["username"],
            "role": user["role"],
        }
    )

    # Audit log
    client_ip = request.client.host if request.client else ""
    await log_action(
        action="LOGIN",
        user_id=str(user["_id"]),
        username=user["username"],
        details=f"User '{user['username']}' logged in." + (" [OFFLINE]" if is_offline else ""),
        ip_address=client_ip,
    )

    return TokenResponse(
        access_token=token,
        user=UserResponse.from_doc(user),
    )


# --------------------------------------------------------------------------
# Current user profile
# --------------------------------------------------------------------------

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Return the profile of the currently authenticated user."""
    return UserResponse.from_doc(current_user)


# --------------------------------------------------------------------------
# User CRUD (admin only)
# --------------------------------------------------------------------------

@router.get("/users", response_model=PaginatedResponse)
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(require_role("admin")),
):
    """Return a paginated list of all users.

    Requires the ``admin`` role.
    """
    users = get_collection("users")
    total = await users.count_documents({})
    skip = (page - 1) * per_page

    cursor = users.find({}).sort("created_at", -1).skip(skip).limit(per_page)
    docs = await cursor.to_list(length=per_page)

    items = [UserResponse.from_doc(d).model_dump() for d in docs]
    return PaginatedResponse.build(items=items, total=total, page=page, per_page=per_page)


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    request: Request,
    current_user: dict = Depends(require_role("admin")),
):
    """Create a new user account.

    Requires the ``admin`` role. Duplicate usernames are rejected.
    """
    users = get_collection("users")

    # Check uniqueness
    existing = await users.find_one({"username": body.username})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Username '{body.username}' already exists.",
        )

    doc = {
        "username": body.username,
        "password": hash_password(body.password),
        "full_name": body.full_name,
        "role": body.role,
        "created_at": datetime.now(timezone.utc),
    }
    result = await users.insert_one(doc)
    doc["_id"] = result.inserted_id

    # Audit log
    client_ip = request.client.host if request.client else ""
    await log_action(
        action="CREATE_USER",
        user_id=str(current_user["_id"]),
        username=current_user["username"],
        details=f"Created user '{body.username}' with role '{body.role}'.",
        ip_address=client_ip,
    )

    return UserResponse.from_doc(doc)


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_user: dict = Depends(require_role("admin")),
):
    """Get details of a single user.
    
    Requires the ``admin`` role.
    """
    users = get_collection("users")
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format.",
        )
        
    user = await users.find_one({"_id": oid})
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
        
    return UserResponse.from_doc(user)


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    body: UserUpdate,
    request: Request,
    current_user: dict = Depends(require_role("admin")),
):
    """Update an existing user's profile or password.

    Requires the ``admin`` role.
    """
    users = get_collection("users")

    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format.",
        )

    update_data: dict = {}
    if body.full_name is not None:
        update_data["full_name"] = body.full_name
    if body.role is not None:
        update_data["role"] = body.role
    if body.password is not None:
        update_data["password"] = hash_password(body.password)

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update.",
        )

    result = await users.find_one_and_update(
        {"_id": oid},
        {"$set": update_data},
        return_document=True,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    # Audit log
    client_ip = request.client.host if request.client else ""
    await log_action(
        action="UPDATE_USER",
        user_id=str(current_user["_id"]),
        username=current_user["username"],
        details=f"Updated user '{user_id}'. Fields: {list(update_data.keys())}.",
        ip_address=client_ip,
    )

    return UserResponse.from_doc(result)


@router.delete("/users/{user_id}", status_code=status.HTTP_200_OK)
async def delete_user(
    user_id: str,
    request: Request,
    current_user: dict = Depends(require_role("admin")),
):
    """Delete a user account.

    Requires the ``admin`` role. A user cannot delete their own account.
    """
    users = get_collection("users")

    if user_id == str(current_user["_id"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account.",
        )

    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format.",
        )

    result = await users.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    # Audit log
    client_ip = request.client.host if request.client else ""
    await log_action(
        action="DELETE_USER",
        user_id=str(current_user["_id"]),
        username=current_user["username"],
        details=f"Deleted user '{user_id}'.",
        ip_address=client_ip,
    )

    return {"message": "User deleted successfully."}

# --------------------------------------------------------------------------
# End Shift (Generate Log)
# --------------------------------------------------------------------------

@router.post("/shift/end")
async def end_shift(request: Request, current_user: dict = Depends(get_current_user)):
    """End the current shift and generate a statistics log."""
    import os
    import re
    from database import get_collection
    orders = get_collection("orders")
    system_logs = get_collection("system_logs")
    
    now = datetime.now(timezone.utc)
    
    # Tìm thời điểm đăng nhập gần nhất
    last_login = await system_logs.find_one(
        {"user_id": str(current_user["_id"]), "action": "LOGIN"},
        sort=[("timestamp", -1)]
    )
    if not last_login:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No login record found for this user.",
        )

    # Tìm thời điểm kết ca gần nhất của người dùng này
    last_end = await system_logs.find_one(
        {"user_id": str(current_user["_id"]), "action": "END_SHIFT"},
        sort=[("timestamp", -1)]
    )
    
    if last_end and last_end["timestamp"] > last_login["timestamp"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Shift already ended for the current login session.",
        )

    if last_end:
        shift_start = last_end["timestamp"]
    else:
        # Nếu chưa từng kết ca, lấy từ đầu ngày
        shift_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    cursor = orders.find({
        "cashier_id": str(current_user["_id"]),
        "created_at": {"$gte": shift_start}
    })
    
    docs = await cursor.to_list(length=None)
    
    total_revenue = 0
    total_cash = 0
    total_transfer = 0
    total_orders = len(docs)
    
    for doc in docs:
        amount = doc.get("total", 0)
        method = doc.get("payment_method")
        total_revenue += amount
        if method == "cash":
            total_cash += amount
        elif method == "split":
            payments = doc.get("payments", [])
            for p in payments:
                if p.get("method") == "cash":
                    total_cash += p.get("amount", 0)
                else:
                    total_transfer += p.get("amount", 0)
        else:
            total_transfer += amount
            
    # Tìm thời điểm đăng nhập thực sự của ca này
    login_log = await system_logs.find_one(
        {
            "user_id": str(current_user["_id"]),
            "action": "LOGIN",
            "timestamp": {"$gte": shift_start}
        },
        sort=[("timestamp", 1)]
    )
    login_time = login_log["timestamp"] if login_log else shift_start
    logout_time = now
    
    if login_time.tzinfo is None:
        login_time = login_time.replace(tzinfo=timezone.utc)
    login_time_local = login_time.astimezone()
    
    if logout_time.tzinfo is None:
        logout_time = logout_time.replace(tzinfo=timezone.utc)
    logout_time_local = logout_time.astimezone()
    
    filename = None
    if total_orders > 0:
        log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        safe_username = re.sub(r'[^a-zA-Z0-9_-]', '', current_user['username'])
        filename = f"shift_{safe_username}_{logout_time_local.strftime('%Y%m%d_%H%M%S')}.log"
        filepath = os.path.join(log_dir, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"SHIFT REPORT\n")
            f.write(f"Cashier: {current_user.get('full_name', current_user['username'])} ({current_user['username']})\n")
            f.write(f"Login Time:  {login_time_local.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Logout Time: {logout_time_local.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("-" * 40 + "\n")
            f.write(f"Total Orders: {total_orders}\n")
            f.write(f"Total Revenue: {total_revenue:,.0f} VND\n")
            f.write(f" - Cash: {total_cash:,.0f} VND\n")
            f.write(f" - Transfer: {total_transfer:,.0f} VND\n")
            f.write("-" * 40 + "\n")
            f.write("Shift ended successfully.\n")
            
    client_ip = request.client.host if request.client else ""
    await log_action(
        action="END_SHIFT",
        user_id=str(current_user["_id"]),
        username=current_user["username"],
        details=f"Ended shift. Orders: {total_orders}, Revenue: {total_revenue:,.0f} VND",
        ip_address=client_ip
    )
        
    return {"message": "Shift ended", "log_file": filename}
