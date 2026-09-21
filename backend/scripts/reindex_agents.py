import config  # noqa: F401; load backend/.env before database imports

import argparse
import asyncio

from db.agents.embeddings import backfill_embeddings, ensure_vector_schema
from db.client import db


async def main(force: bool) -> None:
    await db.connect()
    try:
        await ensure_vector_schema()
        count = await backfill_embeddings(force=force)
        print(f"Indexed {count} agent(s).")
    finally:
        await db.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild agent capability embeddings")
    parser.add_argument("--force", action="store_true", help="re-embed even when hashes match")
    args = parser.parse_args()
    asyncio.run(main(args.force))
