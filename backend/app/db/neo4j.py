"""
Neo4j async driver wrapper.
Manages knowledge graph connections and schema initialization.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase, AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)

_driver: AsyncDriver | None = None


def get_neo4j_driver() -> AsyncDriver:
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            max_connection_pool_size=20,
            connection_timeout=30,
        )
    return _driver


@asynccontextmanager
async def get_neo4j_session() -> AsyncGenerator[AsyncSession, None]:
    driver = get_neo4j_driver()
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        yield session


async def run_query(
    cypher: str,
    params: dict | None = None,
) -> list[dict[str, Any]]:
    """Execute a Cypher query and return results as list of dicts."""
    async with get_neo4j_session() as session:
        result = await session.run(cypher, params or {})
        records = await result.data()
        return records


async def init_constraints() -> None:
    """Create uniqueness constraints and indexes on Neo4j schema."""
    constraints = [
        # Uniqueness constraints
        "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
        "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
        "CREATE CONSTRAINT event_id IF NOT EXISTS FOR (e:Event) REQUIRE e.id IS UNIQUE",
        # Indexes for common lookups
        "CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)",
        "CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.type)",
        "CREATE INDEX entity_canonical IF NOT EXISTS FOR (e:Entity) ON (e.canonical_name)",
        "CREATE INDEX document_type IF NOT EXISTS FOR (d:Document) ON (d.doc_type)",
        "CREATE INDEX event_timestamp IF NOT EXISTS FOR (e:Event) ON (e.timestamp)",
        "CREATE FULLTEXT INDEX entity_search IF NOT EXISTS FOR (e:Entity) ON EACH [e.name, e.canonical_name]",
    ]

    for constraint in constraints:
        try:
            await run_query(constraint)
        except Exception as e:
            if "already exists" not in str(e).lower():
                logger.warning(f"Constraint creation warning: {e}")

    logger.info("Neo4j constraints and indexes initialized")


async def check_connection() -> bool:
    try:
        driver = get_neo4j_driver()
        async with driver.session() as session:
            result = await session.run("RETURN 1 AS ping")
            await result.single()
        return True
    except Exception as e:
        logger.error(f"Neo4j connection failed: {e}")
        return False


async def close_driver() -> None:
    global _driver
    if _driver:
        await _driver.close()
        _driver = None
        logger.info("Neo4j driver closed")
