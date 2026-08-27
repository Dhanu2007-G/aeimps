"""Code Parser — tree-sitter AST for function/class-level chunking."""
from __future__ import annotations
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class CodeParser:
    def __init__(self, language: str = "python"):
        self.language = language

    async def parse(self, file_path: str) -> dict:
        with open(file_path, "r", errors="replace") as f:
            source = f.read()

        code_blocks = self._extract_code_blocks(source, file_path)

        return {
            "text": source,  # Full source as fallback
            "code_blocks": code_blocks,
            "metadata": {
                "language": self.language,
                "file": Path(file_path).name,
                "lines": len(source.splitlines()),
                "functions": len([b for b in code_blocks if b.get("block_type") == "function"]),
            },
        }

    def _extract_code_blocks(self, source: str, file_path: str) -> list[dict]:
        """Extract function and class blocks using tree-sitter."""
        try:
            import tree_sitter_python as tspython
            from tree_sitter import Language, Parser

            PY_LANGUAGE = Language(tspython.language())
            parser = Parser(PY_LANGUAGE)
            tree = parser.parse(source.encode())
            blocks = []

            def visit(node, depth=0):
                if node.type in ("function_definition", "class_definition",
                                  "async_function_definition"):
                    block_text = source[node.start_byte:node.end_byte]
                    blocks.append({
                        "block_type": "function" if "function" in node.type else "class",
                        "content": block_text,
                        "start_line": node.start_point[0] + 1,
                        "end_line": node.end_point[0] + 1,
                        "code_language": self.language,
                    })
                for child in node.children:
                    visit(child, depth + 1)

            visit(tree.root_node)
            return blocks

        except Exception as e:
            logger.debug(f"Tree-sitter parsing failed, using line chunks: {e}")
            # Fallback: split by double newlines
            parts = source.split("\n\n")
            return [
                {"block_type": "block", "content": p, "code_language": self.language}
                for p in parts if p.strip()
            ]
