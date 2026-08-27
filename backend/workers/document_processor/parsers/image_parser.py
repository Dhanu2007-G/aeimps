"""Image Parser — delegates to vision worker for VLM analysis."""
from __future__ import annotations
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ImageParser:
    async def parse(self, file_path: str) -> dict:
        from workers.vision_worker.image_analyzer import ImageAnalyzer
        analyzer = ImageAnalyzer()
        analysis = await analyzer.analyze(file_path)
        return {
            "text": analysis.get("merged_text", ""),
            "image_descriptions": [{
                "description": analysis.get("description", ""),
                "image_type": analysis.get("diagram_type", "unknown"),
                "image_path": file_path,
                "entities": analysis.get("entities", []),
                "page_number": 1,
            }],
            "metadata": {
                "filename": Path(file_path).name,
                "diagram_type": analysis.get("diagram_type", "unknown"),
                "entities_found": len(analysis.get("entities", [])),
            },
        }
