import asyncio
import os
import sys

from motor.motor_asyncio import AsyncIOMotorClient
from bson.objectid import ObjectId
from dotenv import load_dotenv

async def run_migration():
    # Load .env
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    
    mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.environ.get("MONGO_DB_NAME", "evient_pos")
    
    print(f"Connecting to MongoDB: {mongo_uri}")
    client = AsyncIOMotorClient(mongo_uri)
    db = client[db_name]
    
    preorders_col = db["preorders"]
    products_col = db["products"]
    
    # Reset all stock_reserved to 0 first (in case it's run multiple times)
    print("Resetting stock_reserved to 0 for all products...")
    await products_col.update_many({}, {"$set": {"stock_reserved": 0}})
    
    print("Finding pending preorders...")
    pending = await preorders_col.find({"status": "pending"}).to_list(None)
    print(f"Found {len(pending)} pending preorders.")
    
    reserved_map = {}
    
    for doc in pending:
        items = doc.get("items", [])
        for item in items:
            pid = str(item["product_id"])
            qty = item["quantity"]
            if pid not in reserved_map:
                reserved_map[pid] = 0
            reserved_map[pid] += qty
            
    if not reserved_map:
        print("No stock reservations needed.")
        return
        
    print(f"Applying reservations for {len(reserved_map)} products...")
    
    from pymongo import UpdateOne
    bulk_ops = []
    for pid_str, qty in reserved_map.items():
        try:
            pid = ObjectId(pid_str)
            bulk_ops.append(
                UpdateOne({"_id": pid}, {"$set": {"stock_reserved": qty}})
            )
            print(f" - Product {pid_str}: reserve {qty}")
        except Exception as e:
            print(f"Error with product ID {pid_str}: {e}")
            
    if bulk_ops:
        result = await products_col.bulk_write(bulk_ops)
        print(f"Modified {result.modified_count} products.")
        
    print("Migration complete!")
    client.close()

if __name__ == "__main__":
    asyncio.run(run_migration())
