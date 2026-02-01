# -*- coding: utf-8 -*-

import json
import ast
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
from cachetools import TTLCache

import dashvector
from dashtext import SparseVectorEncoder

from competitors_searcher.models.nlp_models import emb_call, rerank_call
from competitors_searcher.parser import generate_results
from competitors_searcher.get_sql import _load_dataframe

# ========================
# 缓存配置
# ========================
_search_cache = TTLCache(maxsize=20000, ttl=7200)
_dv_result_cache: Dict[Tuple[str, str, str, int, str, str], List[Dict[str, Any]]] = {}
_df_cache = TTLCache(maxsize=2, ttl=600)
_meta_cache = TTLCache(maxsize=4, ttl=60)

# ========================
# 配置
# ========================
SQL_PATH = "sql_test.txt"
with open(SQL_PATH, "r", encoding="utf-8") as f:
    SQL = f.read()

DASHVECTOR_COLLECTION = "competitor_products_dev"
DASHVECTOR_API_KEY = "xxx"
DASHVECTOR_ENDPOINT = "xxx"

META_DOC_ID_LATEST = "__meta__#latest"

COL_PRODUCT_ID = "product_id"
COL_COMPANY = "company"
COL_CHANNEL = "channel"
COL_PRODUCT_NAME = "product_name"
COL_TRACK = "track"

TEXT_FIELDS = [
    "labels",
    "features",
    "summary_coverage",
    "summary_liability",
    "summary_exclusions",
    "summary_provisions",
    "summary_services",
]

TOP_K_DASHVECTOR_PER_FIELD = 80
RRF_K = 60.0
MAX_CANDIDATES_FOR_RERANK = 100
DEFAULT_RERANK_THRESHOLD = 0.3

# ========================
# 工具
# ========================
def _now_dt_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _wrap_response_success(detail: Dict[str, Any], biz_dt: str, product_list: List[str], warnings: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "status": "SUCCESS",
        "failCause": "",
        "content": {
            "product_list": product_list,
            "biz_dt": biz_dt,
            "warnings": warnings or [],
        },
        "detail": detail,
    }

def _wrap_response_fail(detail: Dict[str, Any], biz_dt: str, fail_cause: str) -> Dict[str, Any]:
    return {
        "status": "FAIL",
        "failCause": fail_cause or "unknown_error",
        "content": {
            "product_list": [],
            "biz_dt": biz_dt,
            "warnings": [],
        },
        "detail": detail,
    }

def parse_list_like(value: Any) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    s = str(value).strip()
    if not s:
        return ""
    try:
        obj = ast.literal_eval(s)
        if isinstance(obj, (list, tuple)):
            return " ".join(map(str, obj))
    except Exception:
        pass
    return s

def normalize_field_text(field_name: str, value: Any) -> str:
    if field_name in ("labels", "features"):
        return parse_list_like(value)
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    return str(value)

def get_embedding(text: str) -> np.ndarray:
    if not text:
        text = " "
    vec = emb_call(text)
    arr = np.array(vec, dtype="float32")
    norm = np.linalg.norm(arr)
    if norm > 0:
        arr = arr / norm
    return arr

def build_combined_text_from_fields_map(fields_map: Dict[str, Any]) -> str:
    parts: List[str] = []
    for field in TEXT_FIELDS:
        val = normalize_field_text(field, fields_map.get(field, ""))
        if val:
            parts.append(val)
    return "。".join(parts)

def _norm_str_list(items: Optional[List[str]]) -> List[str]:
    if not items:
        return []
    return [str(x).strip() for x in items if str(x).strip()]

def _list_cache_key(items: List[str]) -> str:
    return "|".join(sorted(items))

def _sql_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"

# ========================
# DashVector / DashText
# ========================
_dv_client: Optional[dashvector.Client] = None
_dv_collection = None
_sparse_encoder: Optional[SparseVectorEncoder] = None

def _get_collection():
    global _dv_client, _dv_collection
    if _dv_collection is not None:
        return _dv_collection
    if not DASHVECTOR_API_KEY or not DASHVECTOR_ENDPOINT:
        raise RuntimeError("请先设置 DASHVECTOR_API_KEY 和 DASHVECTOR_ENDPOINT")
    _dv_client = dashvector.Client(api_key=DASHVECTOR_API_KEY, endpoint=DASHVECTOR_ENDPOINT)
    _dv_collection = _dv_client.get(name=DASHVECTOR_COLLECTION)
    if not _dv_collection:
        raise RuntimeError(f"DashVector collection not found: {DASHVECTOR_COLLECTION}")
    return _dv_collection

def _get_sparse_encoder() -> SparseVectorEncoder:
    global _sparse_encoder
    if _sparse_encoder is None:
        _sparse_encoder = SparseVectorEncoder()
        _sparse_encoder.load("./bm25_zh_default.json")
    return _sparse_encoder

def _extract_score(doc: Any) -> float:
    for attr in ("score", "_score", "distance"):
        if hasattr(doc, attr):
            try:
                return float(getattr(doc, attr))
            except Exception:
                pass
    return 0.0

def _safe_get_fields(doc: Any) -> Dict[str, Any]:
    try:
        return dict(getattr(doc, "fields", {}) or {})
    except Exception:
        return {}

# ========================
# biz_dt：从 DashVector meta doc 获取
# ========================
def _get_biz_dt_from_dashvector() -> Tuple[str, List[str]]:
    cache_key = "latest"
    if cache_key in _meta_cache:
        return _meta_cache[cache_key]

    warnings: List[str] = []
    biz_dt = _now_dt_str()

    try:
        col = _get_collection()
        meta_doc = None

        # prefer fetch/get if available
        if hasattr(col, "fetch"):
            fetched = col.fetch([META_DOC_ID_LATEST])
            if fetched and META_DOC_ID_LATEST in fetched:
                meta_doc = fetched[META_DOC_ID_LATEST]

        if meta_doc is None:
            # fallback to query by filter
            qvec = np.zeros((get_embedding("x").shape[0],), dtype="float32")
            ret = col.query(
                vector=qvec,
                topk=1,
                filter=f"is_meta = 1 and meta_type = {_sql_quote('latest')}",
                output_fields=["ingest_dt", "build_id", "data_version"],
                include_vector=False,
            )
            if ret:
                meta_doc = ret[0]

        if meta_doc is not None:
            f = _safe_get_fields(meta_doc)
            ingest_dt = str(f.get("ingest_dt", "")).strip()
            if ingest_dt:
                biz_dt = ingest_dt
            else:
                warnings.append("meta_missing_ingest_dt")
        else:
            warnings.append("meta_doc_not_found")

    except Exception as e:
        warnings.append(f"meta_read_failed:{e}")

    _meta_cache[cache_key] = (biz_dt, warnings)
    return biz_dt, warnings

# ========================
# SQL DF 缓存
# ========================
def _get_df() -> pd.DataFrame:
    key = "df"
    if key in _df_cache:
        return _df_cache[key]
    df = _load_dataframe(SQL)
    if df.index.name != COL_PRODUCT_ID and COL_PRODUCT_ID in df.columns:
        df = df.set_index(COL_PRODUCT_ID)
    _df_cache[key] = df
    return df

def _get_product_row(product_id: str) -> pd.Series:
    df = _get_df()
    if product_id not in df.index:
        raise KeyError(f"product_id={product_id} not found")
    return df.loc[product_id]

# ========================
# DashVector 检索
# ========================
def _build_filter(track: str, field: str, selected_company: List[str], selected_channel: List[str]) -> str:
    clauses = []
    clauses.append("is_meta != 1")
    clauses.append(f"track = {_sql_quote(track)}")
    clauses.append(f"field = {_sql_quote(field)}")
    if selected_company:
        ors = " or ".join([f"company = {_sql_quote(c)}" for c in selected_company])
        clauses.append(f"({ors})")
    if selected_channel:
        ors = " or ".join([f"channel = {_sql_quote(c)}" for c in selected_channel])
        clauses.append(f"({ors})")
    return " and ".join(clauses)

def _dashvector_search(field: str, track: str, query_text: str, top_k: int, selected_company: List[str], selected_channel: List[str]) -> List[Dict[str, Any]]:
    if not query_text.strip():
        return []
    collection = _get_collection()
    encoder = _get_sparse_encoder()
    qvec = get_embedding(query_text).astype("float32")
    q_sparse = encoder.encode_queries(query_text)

    flt = _build_filter(track=track, field=field, selected_company=selected_company, selected_channel=selected_channel)
    ret = collection.query(
        vector=qvec,
        sparse_vector=q_sparse,
        topk=int(top_k),
        filter=flt,
        output_fields=["product_id", "company", "channel", "product_name", "track", "field", "ingest_dt", "build_id", "data_version"],
        include_vector=False,
    )
    if not ret:
        return []

    results: List[Dict[str, Any]] = []
    for doc in ret:
        fields = _safe_get_fields(doc)
        pid = str(fields.get("product_id", "")).strip()
        if not pid:
            did = str(getattr(doc, "id", "") or "")
            pid = did.split("#", 1)[0].strip() if did else ""
        if not pid:
            continue
        results.append({"product_id": pid, "score": _extract_score(doc)})
    return results

def _dashvector_search_cached(field: str, track: str, query_text: str, top_k: int, selected_company: List[str], selected_channel: List[str]) -> List[Dict[str, Any]]:
    ckey = _list_cache_key(selected_company)
    chkey = _list_cache_key(selected_channel)
    key = (field, track, query_text, int(top_k), ckey, chkey)
    if key in _dv_result_cache:
        return _dv_result_cache[key]
    res = _dashvector_search(field, track, query_text, top_k, selected_company, selected_channel)
    _dv_result_cache[key] = res
    return res

# ========================
# RRF
# ========================
def _fuse_with_rrf(route_results: Dict[str, List[Dict[str, Any]]]) -> Tuple[List[Tuple[str, float]], Dict[str, List[Dict[str, Any]]]]:
    agg_scores: Dict[str, float] = defaultdict(float)
    details: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for route_name, cand_list in route_results.items():
        sorted_cands = sorted(cand_list, key=lambda x: x["score"], reverse=True)
        for rank, cand in enumerate(sorted_cands, start=1):
            pid = cand["product_id"]
            agg_scores[pid] += 1.0 / (RRF_K + rank)
            details[pid].append({"route": route_name, "rank": rank, "score_raw": float(cand["score"])})
    return sorted(agg_scores.items(), key=lambda x: x[1], reverse=True), details

# ========================
# Query 校验
# ========================
class QueryValidationError(Exception):
    pass

def _validate_and_normalize_query(query: Dict[str, Any]) -> Dict[str, Any]:
    required_keys = ["product_name", "product_track", "product_info"]
    for k in required_keys:
        if k not in query:
            raise QueryValidationError(f"query 缺少必填字段: {k}")
        if query[k] is None or str(query[k]).strip() == "":
            raise QueryValidationError(f"query 字段 {k} 不能为空")

    product_id = str(query.get("product_id") or "").strip() or None
    selected_company = _norm_str_list(query.get("selected_company", []))
    selected_channel = _norm_str_list(query.get("selected_channel", []))

    return {
        "product_id": product_id,
        "product_name": str(query["product_name"]).strip(),
        "product_track": str(query["product_track"]).strip(),
        "product_info": str(query["product_info"]).strip(),
        "selected_company": selected_company,
        "selected_channel": selected_channel,
    }

# ========================
# 主入口
# ========================
def search_competitors(
    query: Dict[str, Any],
    rerank_threshold: float = DEFAULT_RERANK_THRESHOLD,
    max_results: int = 20,
    selected_company: Optional[List[str]] = None,
    selected_channel: Optional[List[str]] = None,
) -> Dict[str, Any]:
    biz_dt, biz_warnings = _get_biz_dt_from_dashvector()

    try:
        q0 = _validate_and_normalize_query(query)
    except Exception as e:
        detail = {"query_raw": query, "candidates": []}
        return _wrap_response_fail(detail, biz_dt=biz_dt, fail_cause=str(e))

    if selected_company is not None:
        selected_company = _norm_str_list(selected_company)
    else:
        selected_company = q0["selected_company"]

    if selected_channel is not None:
        selected_channel = _norm_str_list(selected_channel)
    else:
        selected_channel = q0["selected_channel"]

    cache_key = json.dumps(
        {
            "product_id": query.get("product_id", ""),
            "product_name": query.get("product_name", ""),
            "product_track": query.get("product_track", ""),
            "product_info": query.get("product_info", ""),
            "selected_company": selected_company,
            "selected_channel": selected_channel,
            "rerank_threshold": rerank_threshold,
            "max_results": max_results,
            "biz_dt": biz_dt,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    if cache_key in _search_cache:
        return _search_cache[cache_key]

    try:
        track = q0["product_track"]
        product_info = q0["product_info"]

        # 1) product_id fallback
        product_row = None
        effective_pid: Optional[str] = None
        if q0["product_id"]:
            try:
                product_row = _get_product_row(q0["product_id"])
                effective_pid = str(product_row.name)
            except Exception:
                product_row = None
                effective_pid = None

        if product_row is not None:
            parsed_fields: Dict[str, Any] = {field: product_row.get(field, "") for field in TEXT_FIELDS}
        else:
            parsed = generate_results(product_info)
            parsed_fields = parsed if isinstance(parsed, dict) else {}
            for field in TEXT_FIELDS:
                parsed_fields.setdefault(field, "")

        normalized_query_fields = {f: normalize_field_text(f, parsed_fields.get(f, "")) for f in TEXT_FIELDS}
        rerank_query_text = build_combined_text_from_fields_map(parsed_fields)

        # 2) multi-route recall
        route_results: Dict[str, List[Dict[str, Any]]] = {}
        futures = {}
        with ThreadPoolExecutor(max_workers=min(8, len(TEXT_FIELDS))) as ex:
            for field in TEXT_FIELDS:
                qtext = normalized_query_fields[field]
                if not qtext.strip():
                    continue
                futures[ex.submit(_dashvector_search_cached, field, track, qtext, TOP_K_DASHVECTOR_PER_FIELD, selected_company, selected_channel)] = f"{field}_dv_hybrid"
            for fut in as_completed(futures):
                route_name = futures[fut]
                try:
                    cand_list = fut.result()
                except Exception:
                    continue
                if cand_list:
                    route_results[route_name] = cand_list

        if not route_results:
            detail = {"query": {**q0, "effective_pid": effective_pid, "parsed_fields": parsed_fields, "rerank_query_text": rerank_query_text}, "candidates": []}
            wrapped = _wrap_response_success(detail, biz_dt=biz_dt, product_list=[], warnings=biz_warnings)
            _search_cache[cache_key] = wrapped
            return wrapped

        # 3) RRF
        fused_scores, route_details = _fuse_with_rrf(route_results)

        df = _get_df()
        allow_company = set(selected_company) if selected_company else None
        allow_channel = set(selected_channel) if selected_channel else None

        candidate_items: List[Dict[str, Any]] = []
        for pid, fused_score in fused_scores:
            if effective_pid is not None and pid == effective_pid:
                continue
            if len(candidate_items) >= MAX_CANDIDATES_FOR_RERANK:
                break
            if pid not in df.index:
                continue
            row = df.loc[pid]
            company = str(row.get(COL_COMPANY, "")).strip()
            channel = str(row.get(COL_CHANNEL, "")).strip()

            if allow_company is not None and company not in allow_company:
                continue
            if allow_channel is not None and channel not in allow_channel:
                continue

            fields_map = {field: row.get(field, "") for field in TEXT_FIELDS}
            combined_text = build_combined_text_from_fields_map(fields_map)
            if not combined_text.strip():
                continue

            candidate_items.append(
                {
                    "product_id": pid,
                    "company": company,
                    "channel": channel,
                    "product_name": str(row.get(COL_PRODUCT_NAME, "")),
                    "product_track": str(row.get(COL_TRACK, "")),
                    "combined_text": combined_text,
                    "fields_map": fields_map,
                    "rrf_score": float(fused_score),
                    "routes": route_details.get(pid, []),
                }
            )

        if not candidate_items:
            detail = {"query": {**q0, "effective_pid": effective_pid, "parsed_fields": parsed_fields, "rerank_query_text": rerank_query_text}, "candidates": []}
            wrapped = _wrap_response_success(detail, biz_dt=biz_dt, product_list=[], warnings=biz_warnings)
            _search_cache[cache_key] = wrapped
            return wrapped

        # 4) rerank
        doc_texts = [item["combined_text"] for item in candidate_items]
        rerank_res = rerank_call(rerank_query_text, doc_texts)
        index_to_score = {int(r["index"]): float(r["score"]) for r in rerank_res}

        final_items: List[Dict[str, Any]] = []
        for idx, item in enumerate(candidate_items):
            score = index_to_score.get(idx)
            if score is None or score < rerank_threshold:
                continue
            final_items.append(
                {
                    "product_id": item["product_id"],
                    "company": item["company"],
                    "channel": item["channel"],
                    "product_name": item["product_name"],
                    "product_track": item["product_track"],
                    "rerank_score": score,
                    "rrf_score": item["rrf_score"],
                    "routes": item["routes"],
                    "evidence": {
                        "combined_text": item["combined_text"],
                        "fields": {f: normalize_field_text(f, item["fields_map"].get(f, "")) for f in TEXT_FIELDS},
                    },
                }
            )

        final_items.sort(key=lambda x: x["rerank_score"], reverse=True)
        if max_results and max_results > 0:
            final_items = final_items[:max_results]

        product_list = [x["product_id"] for x in final_items]

        detail = {"query": {**q0, "effective_pid": effective_pid, "parsed_fields": parsed_fields, "rerank_query_text": rerank_query_text}, "candidates": final_items}
        wrapped = _wrap_response_success(detail, biz_dt=biz_dt, product_list=product_list, warnings=biz_warnings)
        _search_cache[cache_key] = wrapped
        return wrapped

    except Exception as e:
        detail = {"query_raw": query, "candidates": [], "error": str(e)}
        wrapped = _wrap_response_fail(detail, biz_dt=biz_dt, fail_cause=str(e))
        _search_cache[cache_key] = wrapped
        return wrapped
