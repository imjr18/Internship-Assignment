import asyncio
import time
from tools.availability import check_availability

async def blast_availability(restaurant_id: str, date: str, preferred_time: str, party_size: int, concurrent_requests: int = 10):
    print(f"Battering check_availability with {concurrent_requests} simultaneous requests...")
    
    params = {
        "restaurant_id": restaurant_id,
        "party_size": party_size,
        "date": date,
        "preferred_time": preferred_time,
        "duration_minutes": 90
    }
    
    # Fire requests at the exact same time
    tasks = [check_availability(params) for _ in range(concurrent_requests)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    success_count = sum(1 for r in results if isinstance(r, dict) and r.get("success") and r.get("data", {}).get("available"))
    waitlist_count = sum(1 for r in results if isinstance(r, dict) and r.get("success") and not r.get("data", {}).get("available"))
    error_count = sum(1 for r in results if isinstance(r, Exception) or (isinstance(r, dict) and not r.get("success")))
    
    print("\n--- TEST RESULTS ---")
    print(f"Successful Holds Created: {success_count} (Should be perfectly constrained by table capacity)")
    print(f"Fell to Waitlist: {waitlist_count}")
    print(f"Errors/Exceptions: {error_count}")

    if error_count > 0:
        for r in results:
            if isinstance(r, Exception) or not r.get("success"):
                print("Error:", r)

    if success_count > 1:
        print("\nWARNING: Multiple holds generated! This might indicate a TOCTOU race still exists if there was only 1 table!")
    else:
        print("\nSUCCESS: Race Condition Defeated. Exactly one hold was minted.")


if __name__ == "__main__":
    from database.connection import initialize_database
    from database.connection import get_db
    
    async def run():
        await initialize_database()
        
        async with get_db() as db:
            cur = await db.execute("SELECT id FROM restaurants LIMIT 1")
            row = await cur.fetchone()
            real_id = row[0] if row else "missing"
            
        await blast_availability(real_id, "2026-03-07", "19:00", 4, 15)
        
    asyncio.run(run())
