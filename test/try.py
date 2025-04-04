import asyncio

import structlog

from sekaibot.dependencies import solve_dependencies

logger = structlog.get_logger()

class AE(Exception):
    """"""


def a(args: str):
    """"""
    raise AE


async def main():
    """"""
    try:
        deps = await solve_dependencies(a, dependency_cache={str: "a"})
    except Exception as e:
        print(e)
    print(deps)


asyncio.run(main())
