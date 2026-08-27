"""PDF Parser — PyMuPDF for text/images, PaddleOCR for scanned pages."""
from __future__ import annotations
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PDFParser:
    OCR_THRESHOLD = 0.40  # If <40% text chars vs page area → run OCR

    async def parse(self, file_path: str) -> dict:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("pymupdf not installed: pip install pymupdf")

        doc = fitz.open(file_path)
        all_text_parts: list[str] = []
        page_map: dict[int, int] = {}  # char_offset → page_number
        tables: list[dict] = []
        image_descriptions: list[dict] = []
        images_to_ocr: list[tuple[int, bytes]] = []

        char_offset = 0
        for page_num, page in enumerate(doc):
            # Extract text with layout preservation
            text = page.get_text("text", sort=True)

            # Detect image-heavy pages for OCR
            if self._needs_ocr(page, text):
                try:
                    pix = page.get_pixmap(dpi=150)
                    images_to_ocr.append((page_num + 1, pix.tobytes("png")))
                except Exception as e:
                    logger.warning(f"Page {page_num} pixmap failed: {e}")

            # Extract images from page
            for img_index, img in enumerate(page.get_images(full=True)):
                try:
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    if base_image and base_image["size"] > 5000:  # Skip tiny images
                        image_descriptions.append({
                            "page_number": page_num + 1,
                            "image_index": img_index,
                            "description": f"[Image on page {page_num+1}]",
                            "image_bytes_size": base_image["size"],
                        })
                except Exception:
                    pass

            # Track page boundaries in combined text
            if text.strip():
                page_map[char_offset] = page_num + 1
                all_text_parts.append(text)
                char_offset += len(text)

        combined_text = "\n".join(all_text_parts)

        # Run OCR on image-heavy pages
        if images_to_ocr:
            ocr_results = await self._run_ocr(images_to_ocr)
            for page_num, ocr_text in ocr_results:
                if ocr_text.strip():
                    combined_text += f"\n[OCR Page {page_num}]\n{ocr_text}"

        doc.close()
        return {
            "text": combined_text,
            "page_map": page_map,
            "tables": tables,
            "image_descriptions": image_descriptions,
            "metadata": {
                "page_count": len(doc),
                "source": Path(file_path).name,
            },
        }

    def _needs_ocr(self, page, text: str) -> bool:
        """Detect scanned/image-heavy pages requiring OCR."""
        page_area = page.rect.width * page.rect.height
        if page_area <= 0:
            return False
        text_density = len(text) / page_area
        return text_density < self.OCR_THRESHOLD and len(page.get_images()) > 0

    async def _run_ocr(self, pages: list[tuple[int, bytes]]) -> list[tuple[int, str]]:
        """Run PaddleOCR on image bytes."""
        results = []
        try:
            from paddleocr import PaddleOCR
            if not hasattr(self, '_ocr'):
                self._ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)

            import numpy as np
            from PIL import Image
            import io

            for page_num, img_bytes in pages:
                try:
                    img = Image.open(io.BytesIO(img_bytes))
                    img_array = np.array(img)
                    ocr_result = self._ocr.ocr(img_array, cls=True)
                    if ocr_result and ocr_result[0]:
                        lines = [line[1][0] for line in ocr_result[0] if line[1][1] > 0.5]
                        results.append((page_num, " ".join(lines)))
                except Exception as e:
                    logger.warning(f"OCR failed for page {page_num}: {e}")
        except ImportError:
            logger.warning("PaddleOCR not available — skipping OCR")
        except Exception as e:
            logger.error(f"OCR initialization failed: {e}")

        return results
