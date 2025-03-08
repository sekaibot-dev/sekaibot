from sekaibot.dependencies import Depends, solve_dependencies
import anyio

async def get_db_connection() -> str:
    return "Connected to database"

async def query_db(db: str) -> dict:
    return {"db_status": db, "query": "SELECT * FROM users"}

dependency_cache = {
    str: "Connected to database"
}

async def main():
    query_result = await solve_dependencies(query_db, use_cache=True, stack=AsyncExitStack(), dependency_cache=dependency_cache)
    print(query_result)  # 输出: {'db_status': 'Connected to database', 'query': 'SELECT * FROM users'}

anyio.run(main)
