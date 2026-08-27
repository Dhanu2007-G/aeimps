"""Table extractor — detects and extracts structured tables from PDFs."""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


class TableExtractor:
    def extract_from_pdf(self, file_path: str) -> list[dict]:
        tables = []
        try:
            import fitz
            doc = fitz.open(file_path)
            for page_num, page in enumerate(doc):
                # Use PyMuPDF table finder
                try:
                    page_tables = page.find_tables()
                    for i, tbl in enumerate(page_tables):
                        df = tbl.to_pandas()
                        if df.empty:
                            continue
                        tables.append({
                            "page_number": page_num + 1,
                            "table_index": i,
                            "content": df.to_string(index=False),
                            "structured_data": df.to_dict(orient="records"),
                            "rows": len(df),
                            "cols": len(df.columns),
                        })
                except Exception:
                    pass
            doc.close()
        except Exception as e:
            logger.debug(f"Table extraction failed: {e}")
        return tables
