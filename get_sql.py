from __future__ import annotations
from typing import Optional
import os
import pandas as pd

_DEV_SOURCE_CSV = os.getenv("DEV_SOURCE_CSV", "")
_DEV_SINK_CSV = os.getenv("DEV_SINK_CSV", "parsed_output.csv")

def _load_dataframe(sql: str) -> pd.DataFrame:
    if _DEV_SOURCE_CSV and os.path.exists(_DEV_SOURCE_CSV):
        return pd.read_csv(_DEV_SOURCE_CSV)
    return pd.DataFrame(columns=[
        "product_id","company","product_name","channel","track","summary",
        "labels","features","summary_coverage","summary_liability",
        "summary_exclusions","summary_provisions","summary_services",
    ])

def write_dataframe_replace(df: pd.DataFrame, table_name: Optional[str] = None) -> None:
    df.to_csv(_DEV_SINK_CSV, index=False, encoding="utf_8_sig")
