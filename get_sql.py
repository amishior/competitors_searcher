# -*- coding: utf-8 -*-
"""SQL helpers.

Replace these with your real DB accessors:
- _load_dataframe(sql: str) -> DataFrame
- write_dataframe_replace(df: DataFrame, table_name: str = ..., schema: str = ...) -> None

The stubs below read/write local CSV for dev.
"""

from __future__ import annotations
from typing import Optional
import os
import pandas as pd

_DEV_SOURCE_CSV = os.getenv("DEV_SOURCE_CSV", "")
_DEV_SINK_CSV = os.getenv("DEV_SINK_CSV", "parsed_output.csv")

def _load_dataframe(sql: str) -> pd.DataFrame:
    if _DEV_SOURCE_CSV and os.path.exists(_DEV_SOURCE_CSV):
        return pd.read_csv(_DEV_SOURCE_CSV)
    # default empty frame with expected columns
    return pd.DataFrame(columns=[
        "product_id","company","product_name","channel","track","summary",
        "labels","features","summary_coverage","summary_liability",
        "summary_exclusions","summary_provisions","summary_services",
    ])

def write_dataframe_replace(df: pd.DataFrame, table_name: Optional[str] = None) -> None:
    # Replace semantics in DB land. For dev we overwrite a CSV.
    df.to_csv(_DEV_SINK_CSV, index=False, encoding="utf_8_sig")
