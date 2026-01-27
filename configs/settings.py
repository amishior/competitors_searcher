# -*- coding: utf-8 -*-
"""Centralized settings.
Prefer env vars in production; these defaults are for local dev.
"""

import os

# DashVector
DASHVECTOR_API_KEY_ = os.getenv("DASHVECTOR_API_KEY", "xxx")
DASHVECTOR_ENDPOINT_ = os.getenv("DASHVECTOR_ENDPOINT", "xxx")
DASHVECTOR_COLLECTION_ = os.getenv("DASHVECTOR_COLLECTION", "competitor_products_dev")

# Index meta doc id (must match build script)
META_DOC_ID_LATEST = os.getenv("DASHVECTOR_META_LATEST_ID", "__meta__#latest")

# SQL query file path used by retrieval and batch parse (optional)
SQL_QUERY_PATH = os.getenv("SQL_QUERY_PATH", "sql_test.txt")

# Logging
LOG_DIR = os.getenv("LOG_DIR", "./logs")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
