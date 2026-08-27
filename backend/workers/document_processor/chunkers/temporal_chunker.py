"""Temporal Chunker — splits log files by 5-minute time windows."""
from __future__ import annotations
import re
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

TS_PATTERNS = [
    re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'),
    re.compile(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}'),
    re.compile(r'\w{3}\s+\d+\s+\d{2}:\d{2}:\d{2}'),
]
WINDOW_MINUTES = 5


class TemporalChunker:
    def chunk(self, text: str, start_index: int = 0, **kwargs) -> list[dict]:
        lines = text.splitlines()
        windows: list[list[str]] = []
        current_window: list[str] = []
        window_start_ts: datetime | None = None

        for line in lines:
            ts = self._extract_timestamp(line)
            if ts:
                if window_start_ts is None:
                    window_start_ts = ts
                elif (ts - window_start_ts) > timedelta(minutes=WINDOW_MINUTES):
                    if current_window:
                        windows.append(current_window)
                    current_window = []
                    window_start_ts = ts
            current_window.append(line)

            # Max 500 lines per window
            if len(current_window) >= 500:
                windows.append(current_window)
                current_window = []
                window_start_ts = None

        if current_window:
            windows.append(current_window)

        # Fallback: if no timestamps found, use line-count windows
        if not windows:
            for i in range(0, len(lines), 300):
                chunk_lines = lines[i:i+300]
                if chunk_lines:
                    windows.append(chunk_lines)

        chunks = []
        for i, window in enumerate(windows):
            content = "\n".join(window)
            if content.strip():
                chunks.append({
                    "chunk_index": start_index + i,
                    "chunk_type": "log_window",
                    "content": content,
                    "token_count": len(content) // 4,
                    "metadata": {
                        "window_index": i,
                        "line_count": len(window),
                    },
                })
        return chunks

    def _extract_timestamp(self, line: str) -> datetime | None:
        for pattern in TS_PATTERNS:
            m = pattern.search(line)
            if m:
                for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                    try:
                        return datetime.strptime(m.group()[:19], fmt)
                    except ValueError:
                        continue
        return None
