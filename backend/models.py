"""
EViENT POS - Pydantic Models

Defines request / response schemas for every resource in the system:
Users, Products, Orders, Shifts, System Logs, and paginated wrappers.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# User models
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    """Schema for creating a new user account."""
    username: str = Field(..., min_length=3, max_length=50, pattern="^[a-zA-Z0-9_-]+$")
    password: str = Field(..., min_length=6)
    full_name: str = Field(..., min_length=1, max_length=100)
    role: str = Field(default="employee", pattern="^(admin|manager|employee)$")


class UserUpdate(BaseModel):
    """Schema for updating an existing user (all fields optional)."""
    full_name: Optional[str] = Field(default=None, max_length=100)
    role: Optional[str] = Field(default=None, pattern="^(admin|manager|employee)$")
    password: Optional[str] = Field(default=None, min_length=6)


class UserResponse(BaseModel):
    """Public representation of a user (never exposes password hash)."""
    model_config = ConfigDict(populate_by_name=True)

    id: str
    username: str
    full_name: str
    role: str
    created_at: datetime

    @classmethod
    def from_doc(cls, doc: dict) -> "UserResponse":
        """Build a ``UserResponse`` from a raw MongoDB document."""
        doc = dict(doc)
        doc["id"] = str(doc.pop("_id"))
        return cls(**doc)


class UserLogin(BaseModel):
    """Login request payload."""
    username: str
    password: str


class TokenResponse(BaseModel):
    """JWT authentication response returned after successful login."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ---------------------------------------------------------------------------
# Product models
# ---------------------------------------------------------------------------

class ProductCreate(BaseModel):
    """Schema for creating a new product."""
    name: str = Field(..., min_length=1, max_length=200)
    barcode: Optional[str] = Field(default=None, max_length=50)
    price: float = Field(..., ge=0)
    category: Optional[str] = Field(default=None, max_length=100)
    stock: int = Field(default=0, ge=0)
    image_url: Optional[str] = Field(default=None)


class ProductUpdate(BaseModel):
    """Schema for updating a product (all fields optional)."""
    name: Optional[str] = Field(default=None, max_length=200)
    barcode: Optional[str] = Field(default=None, max_length=50)
    price: Optional[float] = Field(default=None, ge=0)
    category: Optional[str] = Field(default=None, max_length=100)
    stock: Optional[int] = Field(default=None, ge=0)
    image_url: Optional[str] = Field(default=None)


class ProductResponse(BaseModel):
    """Public representation of a product."""
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    barcode: Optional[str] = None
    price: float
    category: Optional[str] = None
    stock: int
    image_url: Optional[str] = None
    created_at: datetime

    @classmethod
    def from_doc(cls, doc: dict) -> "ProductResponse":
        """Build a ``ProductResponse`` from a raw MongoDB document."""
        doc = dict(doc)
        doc["id"] = str(doc.pop("_id"))
        return cls(**doc)


# ---------------------------------------------------------------------------
# Order models
# ---------------------------------------------------------------------------

class OrderItem(BaseModel):
    """A single line-item inside an order."""
    product_id: str
    product_name: str
    price: float = Field(..., ge=0)
    quantity: int = Field(..., ge=1)


class PaymentSplit(BaseModel):
    """A single payment split for split-payment orders."""
    method: str
    amount: float = Field(..., ge=0)


class OrderCreate(BaseModel):
    """Schema for creating a new order (list of items + payment method)."""
    items: list[OrderItem] = Field(..., min_length=1)
    payment_method: str = Field(default="cash")
    payments: Optional[list[PaymentSplit]] = None
    amount_given: Optional[float] = None
    expected_change: Optional[float] = None
    actual_change: Optional[float] = None


class OrderResponse(BaseModel):
    """Public representation of a completed order."""
    model_config = ConfigDict(populate_by_name=True)

    id: str
    order_number: str
    items: list[OrderItem]
    subtotal: Optional[float] = None
    vat_rate: Optional[float] = None
    vat_amount: Optional[float] = None
    total: float
    actual_revenue: Optional[float] = None
    payment_method: str
    payments: Optional[list[dict]] = None
    amount_given: Optional[float] = None
    expected_change: Optional[float] = None
    actual_change: Optional[float] = None
    cashier_id: str
    cashier_name: str
    created_at: datetime

    @classmethod
    def from_doc(cls, doc: dict) -> "OrderResponse":
        """Build an ``OrderResponse`` from a raw MongoDB document."""
        doc = dict(doc)
        doc["id"] = str(doc.pop("_id"))
        return cls(**doc)





# ---------------------------------------------------------------------------
# System logs
# ---------------------------------------------------------------------------

class SystemLogResponse(BaseModel):
    """Public representation of a system audit-log entry."""
    model_config = ConfigDict(populate_by_name=True)

    id: str
    action: str
    user_id: str
    username: str
    details: str
    ip_address: str
    timestamp: datetime

    @classmethod
    def from_doc(cls, doc: dict) -> "SystemLogResponse":
        """Build a ``SystemLogResponse`` from a raw MongoDB document."""
        doc = dict(doc)
        doc["id"] = str(doc.pop("_id"))
        return cls(**doc)


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class PaginatedResponse(BaseModel):
    """Generic paginated wrapper around a list of items."""
    items: list[Any]
    total: int
    page: int
    per_page: int
    total_pages: int

    @classmethod
    def build(
        cls,
        items: list[Any],
        total: int,
        page: int,
        per_page: int,
    ) -> "PaginatedResponse":
        """Convenience factory that calculates ``total_pages`` automatically."""
        return cls(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=math.ceil(total / per_page) if per_page > 0 else 0,
        )


# ---------------------------------------------------------------------------
# Drawer models
# ---------------------------------------------------------------------------

class DrawerTransactionCreate(BaseModel):
    """Schema for manual drawer transactions."""
    amount: float = Field(..., description="Amount. Positive for deposit, negative for withdrawal")
    type: str = Field(..., pattern="^(pay_in|pay_out|sale|refund)$")
    note: Optional[str] = None


class DrawerTransactionResponse(BaseModel):
    """Public representation of a drawer transaction."""
    model_config = ConfigDict(populate_by_name=True)

    id: str
    amount: float
    type: str
    note: Optional[str]
    user_id: str
    username: str
    created_at: datetime

    @classmethod
    def from_doc(cls, doc: dict) -> "DrawerTransactionResponse":
        doc = dict(doc)
        doc["id"] = str(doc.pop("_id"))
        return cls(**doc)


class DrawerStateResponse(BaseModel):
    """Public representation of the current drawer state."""
    balance: float
    last_updated: datetime
