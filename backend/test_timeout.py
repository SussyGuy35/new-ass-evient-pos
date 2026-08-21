import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import time

async def main():
    client = AsyncIOMotorClient("mongodb://10.255.255.1:27017", serverSelectionTimeoutMS=30000)
    db = client.test
    
    start = time.time()
    print("Testing wait_for...")
    try:
        async def fetch():
            return await db.test.count_documents({})
        await asyncio.wait_for(fetch(), timeout=2.0)
    except Exception as e:
        print(f"Exception caught! {type(e)}")
    
    print(f"Time taken: {time.time() - start:.2f} seconds")

asyncio.run(main())
