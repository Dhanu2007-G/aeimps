"""Log Parser — format detection, structured parsing, temporal chunking prep."""
from __future__ import annotations
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

LOG_PATTERNS = {
    "json": re.compile(r'^\s*\{.*\}\s*$'),
    "nginx": re.compile(r'(\d{1,3}\.){3}\d{1,3}.*\[.*\].*HTTP'),
    "syslog": re.compile(r'\w{3}\s+\d+\s+\d{2}:\d{2}:\d{2}'),
    "timestamp_kv": re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'),
    "stacktrace": re.compile(r'(Exception|Error|Traceback|at\s+\w+\.)'),
}


class LogParser:
    async def parse(self, file_path: str) -> dict:
        import chardet

        with open(file_path, "rb") as f:
            raw_bytes = f.read()

        enc = chardet.detect(raw_bytes[:8192]).get("encoding", "utf-8") or "utf-8"
        text = raw_bytes.decode(enc, errors="replace")
        lines = text.splitlines()

        # Detect log format
        fmt = self._detect_format(lines[:20])

        # Extract severity buckets
        severity_counts = {"ERROR": 0, "WARN": 0, "INFO": 0, "DEBUG": 0}
        for line in lines:
            upper = line.upper()
            for sev in severity_counts:
                if sev in upper:
                    severity_counts[sev] += 1
                    break

        summary = (
            f"Log file: {Path(file_path).name} | Format: {fmt} | "
            f"Lines: {len(lines)} | "
            f"Errors: {severity_counts['ERROR']} | "
            f"Warnings: {severity_counts['WARN']}\n\n"
        )

        return {
            "text": summary + text,
            "metadata": {
                "log_format": fmt,
                "line_count": len(lines),
                "severity_counts": severity_counts,
                "encoding": enc,
            },
        }

    def _detect_format(self, sample_lines: list[str]) -> str:
        for line in sample_lines:
            for fmt, pattern in LOG_PATTERNS.items():
                if pattern.search(line):
                    return fmt
        return "plaintext"
