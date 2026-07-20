"""
EViENT POS - Authentication & Authorisation Module

Provides password hashing (bcrypt via passlib), JWT token creation / decoding,
a FastAPI dependency to extract the current user from the ``Authorization``
header, and a role-based access-control dependency factory.
"""

from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Callable

import jwt
from bson import ObjectId
from fastapi import Depends, HTTPException, Request, status
import bcrypt

from config import settings
from database import get_collection

# Bcrypt password context -------------------------------------------------

def hash_password(password: str) -> str:
    """Return the bcrypt hash of *password*.

    Args:
        password: The plain-text password to hash.

    Returns:
        A bcrypt hash string.
    """
    # bcrypt requires bytes
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed_bytes.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a bcrypt hash.

    Args:
        plain: The plain-text password.
        hashed: The stored bcrypt hash.

    Returns:
        ``True`` if the password matches, ``False`` otherwise.
    """
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# JWT helpers --------------------------------------------------------------

def create_access_token(data: dict) -> str:
    """Create a signed JWT access token.

    The token includes an ``exp`` claim set to *now + JWT_EXPIRATION* seconds.

    Args:
        data: Payload dictionary to encode in the token.

    Returns:
        The encoded JWT string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(seconds=settings.JWT_EXPIRATION)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token.

    Args:
        token: The encoded JWT string.

    Returns:
        The decoded payload dictionary.

    Raises:
        HTTPException: If the token is expired or invalid.
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
        )


# FastAPI dependencies -----------------------------------------------------

async def get_current_user(request: Request) -> dict:
    """FastAPI dependency that extracts and validates the current user.

    Reads the ``Authorization: Bearer <token>`` header, decodes the JWT,
    and fetches the corresponding user document from MongoDB.

    Args:
        request: The incoming FastAPI request.

    Returns:
        The user document (dict) from the database.

    Raises:
        HTTPException: 401 if the header is missing / invalid / user not found.
    """
    auth_header: str | None = request.headers.get("Authorization")
    token = None

    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
    elif request.query_params.get("token"):
        token = request.query_params.get("token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header.",
        )
    payload = decode_access_token(token)

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload.",
        )

    try:
        users = get_collection("users")
        user = await users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        # MongoDB may be down – try local cache
        user = None

    if user is None:
        # Fallback to local SQLite cache
        try:
            import local_db
            cached = await local_db.get_cached_user_by_id(user_id)
            if cached:
                return cached
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    return user


def require_role(*roles: str) -> Callable:
    """Factory that returns a FastAPI dependency enforcing role-based access.

    Usage::

        @router.get("/admin-only", dependencies=[Depends(require_role("admin"))])
        async def admin_endpoint(): ...

    Args:
        *roles: One or more allowed role strings (e.g. ``"admin"``, ``"manager"``).

    Returns:
        An async dependency callable.
    """

    async def role_checker(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role(s): {', '.join(roles)}.",
            )
        return current_user

    return role_checker
