import os
import time
import uuid
import json
from typing import List, Dict, Any, Optional

import dashvector
from cachetools import TTLCache
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

from competitors_searcher.pipeline.retrieval import search_competitors
from competitors_searcher.pipeline.batch_parse import start_pipeline_task
from competitors_searcher.configs.settings import DASHVECTOR_API_KEY_, DASHVECTOR_ENDPOINT_, DASHVECTOR_COLLECTION_, META_DOC_ID_LATEST
from competitors_searcher.logs.logger_config import get_logger

logger = get_logger("api")

app = FastAPI(
    title="Competitor Retrieval Service",
    version="1.0.0",
    description="提供：索引构建触发/状态查询/竞品检索",
)

# =========================
# DashVector 配置
# =========================
DASHVECTOR_COLLECTION = DASHVECTOR_COLLECTION_
DASHVECTOR_API_KEY = DASHVECTOR_API_KEY_
DASHVECTOR_ENDPOINT = DASHVECTOR_ENDPOINT_

_dv_client: Optional[dashvector.Client] = None
_dv_collection = None
_meta_cache = TTLCache(maxsize=16, ttl=3)

def _get_collection():
    global _dv_client, _dv_collection
    if _dv_collection is not None:
        return _dv_collection

    if not DASHVECTOR_API_KEY or not DASHVECTOR_ENDPOINT:
        raise RuntimeError("DASHVECTOR_API_KEY / DASHVECTOR_ENDPOINT 未设置")

    _dv_client = dashvector.Client(api_key=DASHVECTOR_API_KEY, endpoint=DASHVECTOR_ENDPOINT)
    _dv_collection = _dv_client.get(name=DASHVECTOR_COLLECTION)
    if not _dv_collection:
        raise RuntimeError(f"DashVector collection not found: {DASHVECTOR_COLLECTION}")
    return _dv_collection

def _read_latest_meta() -> Dict[str, Any]:
    cache_key = "latest_meta"
    if cache_key in _meta_cache:
        return _meta_cache[cache_key]

    col = _get_collection()
    # prefer fetch API
    doc = None
    if hasattr(col, "fetch"):
        fetched = col.fetch([META_DOC_ID_LATEST])
        if fetched and META_DOC_ID_LATEST in fetched:
            doc = fetched[META_DOC_ID_LATEST]
    if doc is None:
        raise RuntimeError(f"latest meta doc not found: {META_DOC_ID_LATEST}")

    fields = getattr(doc, "fields", None) or {}
    _meta_cache[cache_key] = fields
    return fields

# =========================
# Logging middleware (safe: does not consume response body)
# =========================
class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("x-trace-id") or uuid.uuid4().hex
        start = time.perf_counter()

        # request preview
        req_preview = ""
        try:
            body = await request.body()
            if body:
                req_preview = body[:4096].decode("utf-8", errors="ignore")
        except Exception:
            req_preview = ""

        logger.info(json.dumps({
            "event": "http_in",
            "trace_id": trace_id,
            "method": request.method,
            "path": request.url.path,
            "query": str(request.url.query),
            "client": getattr(request.client, "host", None),
            "req_preview": req_preview,
        }, ensure_ascii=False))

        try:
            response = await call_next(request)
        except Exception as e:
            cost_ms = int((time.perf_counter() - start) * 1000)
            logger.error(json.dumps({
                "event": "http_err",
                "trace_id": trace_id,
                "method": request.method,
                "path": request.url.path,
                "cost_ms": cost_ms,
                "error": str(e),
            }, ensure_ascii=False), exc_info=True)
            raise

        cost_ms = int((time.perf_counter() - start) * 1000)
        logger.info(json.dumps({
            "event": "http_out",
            "trace_id": trace_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": getattr(response, "status_code", None),
            "cost_ms": cost_ms,
        }, ensure_ascii=False))
        return response

app.add_middleware(AccessLogMiddleware)

# =========================
# Pydantic Models
# =========================
class BuildIndexResponse(BaseModel):
    status: str
    failCause: str
    content: Dict[str, Any]

class IndexStatusResponse(BaseModel):
    status: str
    failCause: str
    content: Dict[str, Any]

class CompetitorQuery(BaseModel):
    product_id: str = Field(default="", description="产品唯一 ID，可为空字符串")
    product_name: str = Field(..., description="产品名称")
    product_track: str = Field(..., description="产品赛道，例如：医疗险、重疾险")
    product_info: str = Field(..., description="产品文本信息")
    selected_company: List[str] = Field(default_factory=list, description="可选：限定公司，为空不过滤")
    selected_channel: List[str] = Field(default_factory=list, description="可选：限定渠道，为空不过滤")
    rerank_threshold: float = Field(default=0.30, ge=0.0, le=1.0, description="重排阈值")
    max_results: int = Field(default=20, ge=1, le=100, description="最大返回条数")

class SearchCompetitorsResponse(BaseModel):
    status: str
    failCause: str
    content: Dict[str, Any]
    detail: Dict[str, Any]

# =========================
# Health
# =========================
@app.get("/health")
def health():
    return {"status": "ok"}

# =========================
# 1) 数据准备
# =========================
@app.post("/v1/index/build", response_model=BuildIndexResponse)
def build_index():
    try:
        logger.info("build_index called")
        return start_pipeline_task()
    except Exception as e:
        logger.error("build failed", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# =========================
# 2) 是否完成（无参，读 latest meta doc）
# =========================
@app.get("/v1/index/status", response_model=IndexStatusResponse)
def index_status():
    try:
        meta = _read_latest_meta()
        ingest_dt = str(meta.get("ingest_dt", "")).strip()

        content = {
            "task_status": "ready" if ingest_dt else "unknown",
            "latest_finished_at": ingest_dt,
            "task_id": meta.get("build_id"),
            "dashvector": {
                "collection": meta.get("collection", DASHVECTOR_COLLECTION),
                "ingest_dt": meta.get("ingest_dt"),
                "data_version": meta.get("data_version"),
                "row_count": meta.get("row_count"),
                "doc_count": meta.get("doc_count"),
                "skipped_docs": meta.get("skipped_docs"),
            },
        }
        logger.info("index_status success")
        return {"status": "SUCCESS", "failCause": "", "content": content}
    except Exception as e:
        logger.error("index_status failed", exc_info=True)
        return {"status": "FAIL", "failCause": str(e), "content": {}}

# =========================
# 3) 竞品发现
# =========================
@app.post("/v1/search_competitors", response_model=SearchCompetitorsResponse)
def search_competitors_endpoint(req: CompetitorQuery):
    logger.info(f"search_competitors request product={req.product_name}")
    try:
        query: Dict[str, Any] = {
            "product_id": req.product_id or "",
            "product_name": req.product_name,
            "product_track": req.product_track,
            "product_info": req.product_info,
            "selected_company": req.selected_company,
            "selected_channel": req.selected_channel,
        }

        result = search_competitors(
            query=query,
            rerank_threshold=req.rerank_threshold,
            max_results=req.max_results,
            selected_company=req.selected_company,
            selected_channel=req.selected_channel,
        )

        if not isinstance(result, dict) or "status" not in result:
            raise RuntimeError("retrieval.search_competitors returned invalid payload (missing 'status').")

        result.setdefault("failCause", "")
        result.setdefault("content", {})
        result.setdefault("detail", {})
        logger.info("search_competitors success")
        return result

    except Exception as e:
        logger.error("search_competitors failed", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
