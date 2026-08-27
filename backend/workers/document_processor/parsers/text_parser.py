"""Text/Markdown parser using Unstructured.io for structure-aware parsing."""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


class TextParser:
    async def parse(self, file_path: str) -> dict:
        # Try Unstructured.io first (best structure detection)
        try:
            from unstructured.partition.auto import partition
            elements = partition(filename=file_path)
            text = "\n\n".join(str(el) for el in elements if str(el).strip())
            return {"text": text, "metadata": {"parser": "unstructured", "elements": len(elements)}}
        except Exception as e:
            logger.debug(f"Unstructured failed, falling back to plain read: {e}")

        # Fallback: plain read
        try:
            import chardet
            with open(file_path, "rb") as f:
                raw = f.read()
            enc = chardet.detect(raw[:8192]).get("encoding", "utf-8") or "utf-8"
            text = raw.decode(enc, errors="replace")
            return {"text": text, "metadata": {"parser": "plain", "encoding": enc}}
        except Exception as e:
            raise RuntimeError(f"Text parsing failed: {e}") from e
