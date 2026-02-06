from typing import Any, Dict, List, Optional

def generate_results(
    product_text: str,
    label_json: Optional[List[Dict[str, str]]] = None,
    max_labels: int = 3,
    timeout_sec: int = 60,
    as_json: bool = True,
) -> Any:
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
