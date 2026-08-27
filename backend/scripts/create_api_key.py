#!/usr/bin/env python3
"""Create an API key for AEIMPS access."""
import asyncio
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


async def create_key(name: str, permissions: list[str]) -> None:
    from app.core.security import generate_api_key
    from app.db.postgres import get_db
    from app.db.models import APIKey

    raw_key, key_hash, key_prefix = generate_api_key()

    async with get_db() as db:
        api_key = APIKey(
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            permissions=permissions,
        )
        db.add(api_key)

    print(f"\n{'='*50}")
    print(f"API Key created: {name}")
    print(f"Key:    {raw_key}")
    print(f"Prefix: {key_prefix}")
    print(f"Perms:  {permissions}")
    print(f"{'='*50}")
    print("⚠  Save this key — it won't be shown again.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True, help="Key name/description")
    parser.add_argument("--permissions", default="read,write", help="Comma-separated permissions")
    args = parser.parse_args()
    asyncio.run(create_key(args.name, args.permissions.split(",")))
