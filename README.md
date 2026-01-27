# competitors_searcher

A minimal, production-ready scaffold for:
- `/v1/index/build` trigger (parse batch -> write SQL replace -> build DashVector index)
- `/v1/index/status` read DashVector latest meta doc
- `/v1/search_competitors` competitor retrieval

## Run (example)

```bash
export DASHVECTOR_API_KEY=...
export DASHVECTOR_ENDPOINT=...
export DASHVECTOR_COLLECTION=competitor_products

uvicorn competitors_searcher.app:app --host 0.0.0.0 --port 9000
```

## Mount into a bigger FastAPI app

```py
from fastapi import FastAPI
from competitors_searcher.app import app as competitors_app

main_app = FastAPI()
main_app.mount("/competitors", competitors_app)
```

Then call:
- `GET /competitors/health`
- `GET /competitors/v1/index/status`
- `POST /competitors/v1/index/build`
- `POST /competitors/v1/search_competitors`
