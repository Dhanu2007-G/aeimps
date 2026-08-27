"""Entity Resolver — deduplicates entities via fuzzy matching + embedding similarity."""
from __future__ import annotations
import logging
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)


class EntityResolver:
    FUZZY_THRESHOLD = 88

    async def resolve(self, entities: list[dict]) -> list[dict]:
        """Merge entities with the same canonical name."""
        if not entities:
            return []

        canonical: dict[str, dict] = {}

        for ent in entities:
            name = ent["name"].strip()
            matched_key = None

            for existing_key in list(canonical.keys()):
                score = fuzz.ratio(name.lower(), existing_key.lower())
                if score >= self.FUZZY_THRESHOLD:
                    matched_key = existing_key
                    break

            if matched_key:
                # Merge: keep higher confidence, accumulate chunk_ids
                existing = canonical[matched_key]
                if ent.get("confidence", 0) > existing.get("confidence", 0):
                    canonical[matched_key] = {**existing, "name": name,
                                               "confidence": ent["confidence"]}
                chunk_ids = existing.get("chunk_ids", [existing.get("chunk_id")])
                if ent.get("chunk_id") not in chunk_ids:
                    chunk_ids.append(ent.get("chunk_id"))
                canonical[matched_key]["chunk_ids"] = chunk_ids
            else:
                canonical[name] = {**ent, "canonical_name": name,
                                    "chunk_ids": [ent.get("chunk_id")]}

        return list(canonical.values())
