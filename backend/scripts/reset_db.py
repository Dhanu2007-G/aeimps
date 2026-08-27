#!/usr/bin/env python3
"""DANGER: Drop and recreate all AEIMPS database state."""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


async def reset():
    from app.db.postgres import get_engine
    from app.db.models import Base
    from app.db.qdrant import get_qdrant_client
    from app.db.neo4j import run_query
    from app.core.config import settings

    # PostgreSQL
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("✓ PostgreSQL reset")

    # Qdrant
    client = get_qdrant_client()
    for col in [settings.QDRANT_COLLECTION_CHUNKS, settings.QDRANT_COLLECTION_IMAGES,
                settings.QDRANT_COLLECTION_ENTITIES]:
        try:
            await client.delete_collection(col)
        except Exception:
            pass
    from app.db.qdrant import init_collections
    await init_collections()
    print("✓ Qdrant reset")

    # Neo4j
    await run_query("MATCH (n) DETACH DELETE n")
    from app.db.neo4j import init_constraints
    await init_constraints()
    print("✓ Neo4j reset")

    print("\nDatabase reset complete.")


if __name__ == "__main__":
    asyncio.run(reset())
