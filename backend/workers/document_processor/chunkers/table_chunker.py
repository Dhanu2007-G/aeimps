"""Table Chunker — each table is one chunk regardless of size."""


class TableChunker:
    def chunk(self, table: dict, start_index: int = 0) -> list[dict]:
        content = table.get("content", "")
        if not content:
            return []
        return [{
            "chunk_index": start_index,
            "chunk_type": "table",
            "content": content,
            "token_count": len(content) // 4,
            "page_number": table.get("page_number"),
            "table_data": table.get("structured_data"),
            "metadata": {"table_index": table.get("table_index", 0)},
        }]
