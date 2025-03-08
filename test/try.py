from sekaibot.dependencies import Depends, solve_dependencies
import anyio
from contextlib import AsyncExitStack

async def get_db_connection() -> str:
    return "Connected to database"

async def query_db(cond: anyio.Condition, db: str = Depends(get_db_connection)) -> dict:
    return {"db_status": db, "query": "SELECT * FROM users", "cond": cond}

dependency_cache = {
    anyio.Condition: anyio.Condition()
}

class A:
    query_db = Depends(query_db)

class B:
    a: A = Depends()

async def main():
    query_result = await solve_dependencies(
        B, 
        use_cache=True, 
        stack=AsyncExitStack(), 
        dependency_cache=dependency_cache
    )
    print(query_result.a.query_db)

anyio.run(main)

