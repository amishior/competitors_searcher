# -*- coding: utf-8 -*-
import json
import logging
import os
import sys
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

from competitors_searcher.configs.settings import LOG_DIR, LOG_LEVEL

def _ensure_log_dir() -> Path:
    p = Path(LOG_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p

def _json_dumps_safe(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return str(obj)

def _kv(event: str, payload: Dict[str, Any]) -> str:
    d = {"event": event, **(payload or {}), "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    return _json_dumps_safe(d)

class JsonLikeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        extra = getattr(record, "extra", None)
        if isinstance(extra, dict):
            base.update(extra)
        if record.exc_info:
            base["exc_info"] = self.formatException(record.exc_info)
        return _json_dumps_safe(base)

def get_logger(name: str = "app") -> logging.Logger:
    """Create/reuse a logger that logs to both console and file in ./logs."""
    logger = logging.getLogger(name)
    if getattr(logger, "_configured", False):
        return logger

    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
    logger.propagate = False

    _ensure_log_dir()
    log_file = os.path.join(LOG_DIR, f"{name}.log")

    fmt = JsonLikeFormatter()


    fh = TimedRotatingFileHandler(
        filename=log_file,
        when="D",
        interval=1,
        backupCount=14,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    fh.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))


    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    sh.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    logger.addHandler(fh)
    logger.addHandler(sh)

    logger._configured = True
    return logger

__all__ = ["get_logger", "_kv"]
