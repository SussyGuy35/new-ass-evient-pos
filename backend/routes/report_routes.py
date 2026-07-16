"""
EViENT POS - Report Routes
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from auth import require_role
from database import get_collection

router = APIRouter(prefix="/reports", tags=["Reports"])

@router.get("/dashboard")
async def get_dashboard_stats(current_user: dict = Depends(require_role("admin", "manager"))):
    orders = get_collection("orders")
    
    now_local = datetime.now().astimezone()
    day_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start = day_start_local.astimezone(timezone.utc)
    
    # Aggregation for standard payment methods
    pipeline_standard = [
        {"$match": {"payment_method": {"$ne": "split"}}},
        {"$group": {
            "_id": "$payment_method",
            "total_revenue": {"$sum": {"$ifNull": ["$actual_revenue", "$total"]}},
            "total_orders": {"$sum": 1}
        }}
    ]
    standard_docs = await orders.aggregate(pipeline_standard).to_list(None)
    
    # Aggregation for split payments
    pipeline_split = [
        {"$match": {"payment_method": "split"}},
        {"$unwind": "$payments"},
        {"$group": {
            "_id": "$payments.method",
            "total_revenue": {"$sum": "$payments.amount"},
            "total_orders": {"$sum": 0} # We don't want to double count orders here
        }}
    ]
    split_docs = await orders.aggregate(pipeline_split).to_list(None)

    # Count total split orders separately
    split_orders_count = await orders.count_documents({"payment_method": "split"})
    
    total_revenue_all = 0
    total_orders_all = split_orders_count
    cash_revenue = 0
    transfer_revenue = 0
    
    for doc in standard_docs + split_docs:
        amount = doc.get("total_revenue", 0)
        count = doc.get("total_orders", 0)
        total_revenue_all += amount
        total_orders_all += count
        
        if doc["_id"] == "cash":
            cash_revenue += amount
        elif doc["_id"] == "bank_transfer":
            transfer_revenue += amount
        else:
            transfer_revenue += amount # Default non-cash to transfer for legacy data

    # Aggregation for today's stats
    pipeline_today = [
        {"$match": {"created_at": {"$gte": day_start}}},
        {"$group": {
            "_id": None,
            "total_revenue": {"$sum": {"$ifNull": ["$actual_revenue", "$total"]}},
            "total_orders": {"$sum": 1}
        }}
    ]
    today_docs = await orders.aggregate(pipeline_today).to_list(None)
    today_revenue = 0
    today_orders = 0
    if today_docs:
        today_revenue = today_docs[0].get("total_revenue", 0)
        today_orders = today_docs[0].get("total_orders", 0)
        
    # Top 5 products
    pipeline_top_products = [
        {"$unwind": "$items"},
        {"$group": {
            "_id": "$items.product_id",
            "name": {"$first": "$items.product_name"},
            "quantity_sold": {"$sum": "$items.quantity"},
            "revenue": {"$sum": {"$multiply": ["$items.price", "$items.quantity"]}}
        }},
        {"$sort": {"quantity_sold": -1}},
        {"$limit": 5}
    ]
    top_products_docs = await orders.aggregate(pipeline_top_products).to_list(None)
    
    return {
        "today": {
            "revenue": today_revenue,
            "orders": today_orders
        },
        "all_time": {
            "revenue": total_revenue_all,
            "orders": total_orders_all,
            "cash_revenue": cash_revenue,
            "transfer_revenue": transfer_revenue
        },
        "top_products": [
            {
                "id": p["_id"],
                "name": p["name"],
                "quantity": p["quantity_sold"],
                "revenue": p["revenue"]
            } for p in top_products_docs
        ]
    }
