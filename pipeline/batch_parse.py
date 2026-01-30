# -*- coding: utf-8 -*-
import threading
import uuid
import json
import ast
from datetime import datetime
from typing import Dict, Any, List, Optional

import pandas as pd

from competitors_searcher.parser import generate_results
from competitors_searcher.get_sql import _load_dataframe, write_dataframe_replace
from competitors_searcher.logs.logger_config import get_logger
import competitors_searcher.build_dashvector_indices as index_builder

logger = get_logger("batch_parse")

_TASKS: Dict[str, Dict[str, Any]] = {}
_TASK_LOCK = threading.Lock()

LIST_KEYS = ["labels", "features"]
SUMMARY_TEXT_KEYS = [
    "summary_coverage",
    "summary_liability",
    "summary_exclusions",
    "summary_provisions",
    "summary_services",
]

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _ensure_dict(res: Any) -> Dict[str, Any]:
    if isinstance(res, dict):
        return res
    if isinstance(res, str):
        try:
            return json.loads(res)
        except Exception:
            return {}
    return {}

def _coerce_to_list(maybe_list) -> List[str]:
    if isinstance(maybe_list, list):
        return [x for x in maybe_list if isinstance(x, str) and x]
    if isinstance(maybe_list, str):
        raw = maybe_list.strip()
        # json list
        try:
            val = json.loads(raw)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, str) and x]
        except Exception:
            pass
        # python literal list
        try:
            val = ast.literal_eval(raw)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, str) and x]
        except Exception:
            pass
        # fallback split
        txt = raw.strip("[]").replace("'", "").replace('"', "")
        return [p.strip() for p in txt.split(",") if p.strip()]
    return []

def _extract_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {k: [] for k in LIST_KEYS}
    out.update({k: "" for k in SUMMARY_TEXT_KEYS})

    for k in LIST_KEYS:
        out[k] = _coerce_to_list(data.get(k, []))

    for k in SUMMARY_TEXT_KEYS:
        v = data.get(k, "")
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()

    if any(not out[k] for k in SUMMARY_TEXT_KEYS) and isinstance(data.get("summary"), dict):
        cn = data["summary"]
        mapping = {
            "保障范围": "summary_coverage",
            "保险责任": "summary_liability",
            "除外责任": "summary_exclusions",
            "特约须知": "summary_provisions",
            "增值服务": "summary_services",
        }
        for k_cn, k_en in mapping.items():
            if not out[k_en]:
                v = cn.get(k_cn)
                if isinstance(v, str) and v.strip():
                    out[k_en] = v.strip()
    return out

def _new_task(task_id: str):
    with _TASK_LOCK:
        _TASKS[task_id] = {
            "task_id": task_id,
            "task_status": "running",
            "started_at": _now(),
            "finished_at": None,
            "error": None,
        }

def _finish_task(task_id: str):
    with _TASK_LOCK:
        if task_id in _TASKS:
            _TASKS[task_id]["task_status"] = "success"
            _TASKS[task_id]["finished_at"] = _now()

def _fail_task(task_id: str, error: str):
    with _TASK_LOCK:
        if task_id in _TASKS:
            _TASKS[task_id]["task_status"] = "fail"
            _TASKS[task_id]["finished_at"] = _now()
            _TASKS[task_id]["error"] = error

def _run_parse_job():
    logger.info("[Pipeline] Step1: parse batch start")
    sql_path = "sql_test.txt"
    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()
    df = _load_dataframe(sql)

    rows = []
    text_col = "summary" if "summary" in df.columns else ("product_text" if "product_text" in df.columns else None)
    if not text_col:
        raise RuntimeError("Input DataFrame missing text column: expected 'summary' or 'product_text'")

    for text in df[text_col].fillna("").astype(str).tolist():
        try:
            res = generate_results(text)
            data = _ensure_dict(res)
            fields = _extract_fields(data)
        except Exception:
            fields = {k: [] for k in LIST_KEYS}
            fields.update({k: "" for k in SUMMARY_TEXT_KEYS})
        rows.append(fields)

    parsed_df = pd.DataFrame(rows)
    final_df = pd.concat([df.reset_index(drop=True), parsed_df], axis=1)
    final_df["create_time"] = _now()

    logger.info("[Pipeline] writing parsed results to SQL (replace)")
    write_dataframe_replace(final_df)

    logger.info("[Pipeline] Step1: parse batch done")

def _run_index_job():
    logger.info("[Pipeline] Step2: build dashvector index start")
    index_builder.main()
    logger.info("[Pipeline] Step2: build dashvector index done")

def _pipeline_runner(task_id: str):
    try:
        logger.info(f"[Task {task_id}] pipeline started")
        _run_parse_job()
        _run_index_job()
        _finish_task(task_id)
        logger.info(f"[Task {task_id}] pipeline success")
    except Exception as e:
        _fail_task(task_id, str(e))
        logger.error(f"[Task {task_id}] pipeline failed: {e}", exc_info=True)

def start_pipeline_task() -> Dict[str, Any]:
    task_id = str(uuid.uuid4())
    _new_task(task_id)

    t = threading.Thread(target=_pipeline_runner, args=(task_id,), daemon=True)
    t.start()

    return {
        "status": "SUCCESS",
        "failCause": "",
        "content": {
            "task_status": "running",
            "task_id": task_id,
            "started_at": _TASKS[task_id]["started_at"],
        },
    }

def get_task_status(task_id: str) -> Dict[str, Any]:
    task = _TASKS.get(task_id)
    if not task:
        return {"status": "FAIL", "failCause": "TASK_NOT_FOUND", "content": {}}
    return {"status": "SUCCESS", "failCause": "", "content": task}
