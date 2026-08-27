"""Metadata extractor — file-level metadata from various sources."""
from __future__ import annotations
import os
from datetime import datetime
from pathlib import Path


class MetadataExtractor:
    def extract(self, file_path: str, doc_type: str) -> dict:
        stat = os.stat(file_path)
        meta = {
            "filename": Path(file_path).name,
            "file_size": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "doc_type": doc_type,
        }
        if doc_type == "pdf":
            try:
                import fitz
                doc = fitz.open(file_path)
                pdf_meta = doc.metadata
                meta.update({k: v for k, v in pdf_meta.items() if v})
                meta["page_count"] = len(doc)
                doc.close()
            except Exception:
                pass
        return meta
