import asyncio

from app.agent.pipeline import investigate_cluster
from app.db.session import AsyncSessionLocal


async def main():
    async with AsyncSessionLocal() as session:
        result = await investigate_cluster(
            "cc-0046",
            session=session,
        )

    print("\n========== GEMINI INVESTIGATION ==========\n")

    if result is None:
        print("ERROR: Cluster cc-0046 was not found.")
        return

    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())