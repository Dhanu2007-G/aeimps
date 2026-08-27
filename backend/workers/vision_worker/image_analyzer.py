"""Image Analyzer — orchestrates VL inference into structured analysis."""
from __future__ import annotations
import json
import logging
import re
from workers.vision_worker.qwen_vl import QwenVL

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """Analyze this enterprise image carefully. Extract:
1. All visible text (verbatim)
2. All system/component/service names
3. All relationships shown (arrows, connections, dependencies)
4. All metrics or values shown
5. Any error messages or warnings
6. The type of image (architecture_diagram / dashboard / screenshot / chart / whiteboard / document_scan / photo)
7. A structured description for semantic search

Respond ONLY with valid JSON:
{
  "diagram_type": "...",
  "description": "detailed description for search",
  "text_overlay": "all visible text",
  "entities": ["list", "of", "named", "things"],
  "relationships": [{"from": "A", "to": "B", "type": "depends_on"}],
  "metrics": {},
  "error_messages": []
}"""


class ImageAnalyzer:
    def __init__(self, model: QwenVL | None = None):
        self._model = model or QwenVL()

    async def analyze(self, image_path: str) -> dict:
        raw = await self._model.analyze_image(image_path, ANALYSIS_PROMPT)
        structured = self._parse_response(raw)

        # Get visual embedding
        visual_emb = self._model.get_clip_embedding(image_path)

        # Get text embedding of description
        text_emb = []
        try:
            from workers.embedding_worker.encoder import get_encoder
            enc = get_encoder()
            desc = structured.get("description", structured.get("text_overlay", ""))
            if desc:
                text_emb = enc.encode_dense([desc])[0]
        except Exception:
            pass

        return {
            **structured,
            "visual_embedding": visual_emb,
            "text_embedding": text_emb,
            "merged_text": self._merge_text(structured),
        }

    def _parse_response(self, raw: str) -> dict:
        try:
            clean = re.sub(r"```(?:json)?\n?(.*?)```", r"\1", raw, flags=re.DOTALL).strip()
            return json.loads(clean)
        except Exception:
            return {
                "diagram_type": "unknown",
                "description": raw[:500] if raw else "Image analysis unavailable",
                "text_overlay": "",
                "entities": [],
                "relationships": [],
            }

    def _merge_text(self, structured: dict) -> str:
        parts = []
        if structured.get("description"):
            parts.append(structured["description"])
        if structured.get("text_overlay"):
            parts.append(f"Text: {structured['text_overlay']}")
        if structured.get("entities"):
            parts.append(f"Entities: {', '.join(structured['entities'])}")
        return "\n".join(parts)
