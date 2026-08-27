"""CSV Parser — schema inference, statistical summary, semantic enrichment."""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


class CSVParser:
    async def parse(self, file_path: str) -> dict:
        import pandas as pd
        import chardet

        # Detect encoding
        with open(file_path, "rb") as f:
            raw = f.read(65536)
        enc = chardet.detect(raw).get("encoding", "utf-8") or "utf-8"

        try:
            df = pd.read_csv(file_path, encoding=enc, nrows=10000)
        except Exception as e:
            logger.warning(f"CSV read failed with {enc}, retrying utf-8: {e}")
            df = pd.read_csv(file_path, encoding="utf-8", errors="replace", nrows=10000)

        # Schema description
        schema_lines = [f"CSV file with {len(df)} rows and {len(df.columns)} columns.\n"]
        schema_lines.append("Columns: " + ", ".join(df.columns.tolist()))

        # Statistical summary for numeric columns
        for col in df.select_dtypes(include="number").columns[:10]:
            stats = df[col].describe()
            schema_lines.append(
                f"Column '{col}' (numeric): "
                f"min={stats['min']:.2f}, max={stats['max']:.2f}, "
                f"mean={stats['mean']:.2f}, nulls={df[col].isna().sum()}"
            )

        # Categorical summary
        for col in df.select_dtypes(include="object").columns[:10]:
            unique_count = df[col].nunique()
            schema_lines.append(
                f"Column '{col}' (text): {unique_count} unique values, "
                f"sample: {df[col].dropna().head(3).tolist()}"
            )

        # Sample rows as text
        sample_text = df.head(5).to_string(index=False)
        full_text = "\n".join(schema_lines) + f"\n\nSample rows:\n{sample_text}"

        return {
            "text": full_text,
            "metadata": {
                "row_count": len(df),
                "column_count": len(df.columns),
                "columns": df.columns.tolist(),
                "encoding": enc,
            },
        }
