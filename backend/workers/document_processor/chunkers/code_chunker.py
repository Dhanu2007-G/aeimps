"""Code Chunker — one chunk per function/class/block."""


class CodeChunker:
    def chunk(self, block: dict, start_index: int = 0) -> list[dict]:
        content = block.get("content", "").strip()
        if not content:
            return []
        return [{
            "chunk_index": start_index,
            "chunk_type": "code",
            "content": content,
            "token_count": len(content) // 4,
            "code_language": block.get("code_language", "unknown"),
            "metadata": {
                "block_type": block.get("block_type", "block"),
                "start_line": block.get("start_line"),
                "end_line": block.get("end_line"),
            },
        }]
