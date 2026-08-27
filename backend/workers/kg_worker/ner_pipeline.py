"""NER Pipeline — spaCy + custom enterprise entity patterns."""
from __future__ import annotations
import logging
import re

logger = logging.getLogger(__name__)

CUSTOM_PATTERNS = [
    # Error codes: HTTP status, exception names
    re.compile(r'\b(HTTP\s*[45]\d\d|[A-Z][a-zA-Z]+(?:Error|Exception|Fault|Timeout))\b'),
    # Version strings
    re.compile(r'\bv?\d+\.\d+(?:\.\d+)?(?:-[a-z0-9]+)?\b'),
    # Service names (lowercase-hyphenated)
    re.compile(r'\b[a-z][a-z0-9]*(?:-[a-z][a-z0-9]+){1,4}-(?:service|api|worker|svc|db|cache)\b'),
    # IP addresses
    re.compile(r'\b\d{1,3}(?:\.\d{1,3}){3}\b'),
    # Environment variables
    re.compile(r'\b[A-Z][A-Z0-9_]{3,}(?:_URL|_KEY|_HOST|_PORT|_SECRET)\b'),
]


class NERPipeline:
    def __init__(self):
        self._nlp = None

    async def setup(self) -> None:
        try:
            import spacy
            try:
                self._nlp = spacy.load("en_core_web_trf")
                logger.info("spaCy transformer model loaded")
            except Exception:
                self._nlp = spacy.load("en_core_web_sm")
                logger.info("spaCy sm model loaded (trf not available)")
        except Exception as e:
            logger.warning(f"spaCy not available: {e} — using pattern-only NER")

    async def extract(self, text: str, chunk_id: str) -> list[dict]:
        """Extract entities from text. Returns list of entity dicts."""
        entities: list[dict] = []

        # spaCy NER
        if self._nlp:
            try:
                doc = self._nlp(text[:5000])  # Limit for speed
                spacy_label_map = {
                    "ORG": "ORGANIZATION", "PRODUCT": "TECHNOLOGY",
                    "PERSON": "PERSON", "GPE": "LOCATION",
                    "FAC": "SYSTEM", "WORK_OF_ART": "CONCEPT",
                }
                for ent in doc.ents:
                    mapped = spacy_label_map.get(ent.label_, "CONCEPT")
                    entities.append({
                        "name": ent.text,
                        "type": mapped,
                        "chunk_id": chunk_id,
                        "confidence": 0.85,
                        "source": "spacy",
                    })
            except Exception as e:
                logger.debug(f"spaCy extraction error: {e}")

        # Custom pattern NER
        for pattern in CUSTOM_PATTERNS:
            for match in pattern.finditer(text):
                name = match.group().strip()
                if len(name) > 2:
                    etype = self._classify_pattern(name)
                    entities.append({
                        "name": name,
                        "type": etype,
                        "chunk_id": chunk_id,
                        "confidence": 0.75,
                        "source": "pattern",
                    })

        # Deduplicate by name
        seen = set()
        unique = []
        for e in entities:
            key = e["name"].lower()
            if key not in seen:
                seen.add(key)
                unique.append(e)

        return unique

    def _classify_pattern(self, name: str) -> str:
        if re.match(r'HTTP', name, re.I) or "Error" in name or "Exception" in name:
            return "ERROR_CODE"
        if re.match(r'v?\d+\.\d+', name):
            return "VERSION"
        if name.endswith(("-service", "-api", "-svc", "-worker", "-db", "-cache")):
            return "SYSTEM"
        if re.match(r'\d+\.\d+\.\d+\.\d+', name):
            return "NETWORK_ADDRESS"
        if name.isupper() and "_" in name:
            return "CONFIGURATION_KEY"
        return "TECHNOLOGY"
