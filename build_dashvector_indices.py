# -*- coding: utf-8 -*-

import os
import ast
import uuid
from datetime import datetime
from typing import Any, Dict, List

import numpy as np
import pandas as pd

import dashvector
from dashvector import Doc

from dashtext import SparseVectorEncoder
from competitors_searcher.get_sql import _load_dataframe
from competitors_searcher.models.nlp_models import emb_call

# ========================
# 配置区
# ========================

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

SQL_PATH = os.getenv("SQL_QUERY_PATH", "sql_test.txt")
with open(SQL_PATH, "r", encoding="utf-8") as f:
    SQL = f.read()

# DashVector
DASHVECTOR_API_KEY = os.getenv("DASHVECTOR_API_KEY", "xxxx")
DASHVECTOR_ENDPOINT = os.getenv("DASHVECTOR_ENDPOINT", "xxxx")
COLLECTION_NAME = os.getenv("DASHVECTOR_COLLECTION", "competitor_products_dev")

# 批量写入
BATCH_DOCS = int(os.getenv("DASHVECTOR_UPSERT_BATCH", "64"))

# Encoder 模式
TRAIN_ENCODER = int(os.getenv("TRAIN_ENCODER", "0"))

# meta doc 配置
META_DOC_ID_LATEST = "__meta__#latest"
META_DOC_ID_PREFIX = "__meta__#build_"

# ========================
# 工具函数
# ========================

def now_dt_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def parse_list_like(value: Any) -> str:
    if pd.isna(value):
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

def normalize_text(field_name: str, value: Any) -> str:
    if field_name in ("labels", "features"):
        return parse_list_like(value)
    if pd.isna(value):
        return ""
    return str(value)

def l2_normalize(vec: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        return vec / norm
    return vec

def get_embedding(text: str) -> List[float]:
    if not text:
        text = " "
    v = emb_call(text)
    arr = np.array(v, dtype="float32")
    arr = l2_normalize(arr)
    return arr.tolist()

def is_valid_text(text: str) -> bool:
    if not text:
        return False
    return bool(str(text).strip())

def build_encoder(df: pd.DataFrame) -> SparseVectorEncoder:
    encoder = SparseVectorEncoder()
    encoder.load("./bm25_zh_default.json")

    if not TRAIN_ENCODER:
        return encoder

    corpus: List[str] = []
    for _, row in df.iterrows():
        parts = []
        for f in TEXT_FIELDS:
            parts.append(normalize_text(f, row.get(f, "")))
        doc = "\n".join([p for p in parts if is_valid_text(p)])
        if is_valid_text(doc):
            corpus.append(doc)

    if corpus:
        encoder.train(corpus)

    return encoder

def ensure_collection(client: dashvector.Client, dim: int) -> Any:
    col = client.get(COLLECTION_NAME)
    if not col:
        raise RuntimeError("collection created but cannot be fetched")
    return col

def flush_upsert(collection: Any, docs: List[Doc]) -> None:
    if not docs:
        return
    ret = collection.upsert(docs)
    if not ret:
        raise RuntimeError(f"upsert failed: {ret}")

def build_meta_docs(
    dim: int,
    build_id: str,
    data_version: str,
    ingest_dt: str,
    total_docs: int,
    skipped_docs: int,
    row_count: int,
) -> List[Doc]:
    zero_vec = [0.0] * dim

    base_fields = {
        "is_meta": 1,
        "ingest_dt": ingest_dt,
        "build_id": build_id,
        "data_version": data_version,
        "row_count": int(row_count),
        "doc_count": int(total_docs),
        "skipped_docs": int(skipped_docs),
        "collection": COLLECTION_NAME,
    }

    latest = Doc(
        id=META_DOC_ID_LATEST,
        vector=zero_vec,
        fields={**base_fields, "meta_type": "latest"},
    )

    hist = Doc(
        id=f"{META_DOC_ID_PREFIX}{build_id}",
        vector=zero_vec,
        fields={**base_fields, "meta_type": "history"},
    )
    return [latest, hist]

def main():
    if not DASHVECTOR_API_KEY or not DASHVECTOR_ENDPOINT:
        raise RuntimeError("请先设置 DASHVECTOR_API_KEY 和 DASHVECTOR_ENDPOINT（DashVector Cluster Endpoint）")

    ingest_dt = now_dt_str()
    build_id = uuid.uuid4().hex
    data_version = os.getenv("DATA_VERSION", "") or datetime.now().strftime("v%Y%m%d_%H%M%S")

    print(f"[Run] ingest_dt={ingest_dt} build_id={build_id} data_version={data_version}")

    print("[Main] 读取 SQL 结果集...")
    df = _load_dataframe(SQL)
    print(f"[Main] 共 {len(df)} 条产品记录。")

    print("[Main] 初始化 DashText SparseVectorEncoder...")
    encoder = build_encoder(df)
    print(f"[Main] Encoder ready. TRAIN_ENCODER={TRAIN_ENCODER}")

    print("[Main] 调用一次 emb_call 获取向量维度...")
    test_vec = np.array(emb_call("测试向量维度"), dtype="float32")
    dim = int(test_vec.shape[0])
    print(f"[Main] 向量维度: {dim}")

    print("[Main] 初始化 DashVector Client...")
    client = dashvector.Client(api_key=DASHVECTOR_API_KEY, endpoint=DASHVECTOR_ENDPOINT)

    print(f"[Main] 确保 Collection 存在：{COLLECTION_NAME}")
    collection = ensure_collection(client, dim)

    print("[Main] 开始 upsert：每个 product 拆成 7 条 Doc（product_id#field）...")
    buffer: List[Doc] = []
    total_docs = 0
    skipped_docs = 0

    has_channel_col = (COL_CHANNEL in df.columns)

    for _, row in df.iterrows():
        product_id = str(row.get(COL_PRODUCT_ID, "")).strip()
        company = str(row.get(COL_COMPANY, "")).strip()
        product_name = str(row.get(COL_PRODUCT_NAME, "")).strip()
        track = str(row.get(COL_TRACK, "")).strip()
        channel = str(row.get(COL_CHANNEL, "")).strip() if has_channel_col else ""

        if not product_id:
            continue

        for field in TEXT_FIELDS:
            raw_text = normalize_text(field, row.get(field, ""))
            if not is_valid_text(raw_text):
                skipped_docs += 1
                continue

            doc_id = f"{product_id}#{field}"
            dense = get_embedding(raw_text)
            sparse = encoder.encode_documents(raw_text)

            doc = Doc(
                id=doc_id,
                vector=dense,
                sparse_vector=sparse,
                fields={
                    "product_id": product_id,
                    "company": company,
                    "channel": channel,
                    "product_name": product_name,
                    "track": track,
                    "field": field,
                    "text": raw_text,
                    "ingest_dt": ingest_dt,
                    "build_id": build_id,
                    "data_version": data_version,
                    "is_meta": 0,
                },
            )
            buffer.append(doc)
            total_docs += 1

            if len(buffer) >= BATCH_DOCS:
                flush_upsert(collection, buffer)
                print(f"[Upsert] 已写入 {total_docs} docs...")
                buffer = []

    if buffer:
        flush_upsert(collection, buffer)

    meta_docs = build_meta_docs(
        dim=dim,
        build_id=build_id,
        data_version=data_version,
        ingest_dt=ingest_dt,
        total_docs=total_docs,
        skipped_docs=skipped_docs,
        row_count=len(df),
    )
    flush_upsert(collection, meta_docs)

    print(f"[Done] 写入完成。total_docs={total_docs}, skipped_docs={skipped_docs}")
    print(f"[Done] Collection: {COLLECTION_NAME}")
    print(f"[Done] Meta updated: {META_DOC_ID_LATEST} and {META_DOC_ID_PREFIX}{build_id}")
    print(f"[Done] biz_dt/ingest_dt={ingest_dt}")

if __name__ == "__main__":
    main()
