# -*- coding: utf-8 -*-
"""Parser stub.

Replace generate_results() with your real parser that extracts:
labels/features/summary_* fields. This stub returns empty outputs.
"""

from typing import Any, Dict, List, Optional

def generate_results(
    product_text: str,
    label_json: Optional[List[Dict[str, str]]] = None,
    max_labels: int = 3,
    timeout_sec: int = 60,
    as_json: bool = True,
) -> Any:
    # ---- STUB ----
    data = {
        "labels": [],
        "features": [],
        "summary_coverage": "",
        "summary_liability": "",
        "summary_exclusions": "",
        "summary_provisions": "",
        "summary_services": "",
    }
    return data
