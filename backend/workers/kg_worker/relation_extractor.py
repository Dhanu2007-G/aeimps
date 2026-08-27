"""Relation extractor — pattern-based + LLM for complex passages."""
from __future__ import annotations
import logging
import re

logger = logging.getLogger(__name__)

RELATION_PATTERNS = [
    (re.compile(r'(\w[\w\-\.]+)\s+(?:depends on|requires|needs)\s+([\w\-\.]+)', re.I), 'DEPENDS_ON'),
    (re.compile(r'(\w[\w\-\.]+)\s+(?:caused?|triggers?|leads? to)\s+([\w\-\.]+)', re.I), 'CAUSES'),
    (re.compile(r'(\w[\w\-\.]+)\s+(?:calls?|invokes?|connects? to)\s+([\w\-\.]+)', re.I), 'CALLS'),
    (re.compile(r'(\w[\w\-\.]+)\s+(?:runs? on|deploys? to|hosts?)\s+([\w\-\.]+)', re.I), 'DEPLOYED_ON'),
    (re.compile(r'(\w[\w\-\.]+)\s+(?:resolves?|fixes?|mitigates?)\s+([\w\-\.]+)', re.I), 'RESOLVES'),
]


class RelationExtractor:
    async def extract(self, text: str, entities: list[dict]) -> list[dict]:
        relations = []
        entity_names = {e["name"].lower() for e in entities}

        for pattern, rel_type in RELATION_PATTERNS:
            for m in pattern.finditer(text):
                subj, obj = m.group(1), m.group(2)
                if subj.lower() in entity_names or obj.lower() in entity_names:
                    relations.append({
                        "subject": subj, "relation": rel_type,
                        "object": obj, "confidence": 0.75,
                    })

        return relations[:50]  # Cap to avoid noise
