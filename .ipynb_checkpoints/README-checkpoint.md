```markdown
<div align="center">

# 🎯 Competitors Searcher

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-green)](https://fastapi.tiangolo.com)
[![DashVector](https://img.shields.io/badge/VectorDB-DashVector-orange)](https://dashvector.console.aliyun.com)

**Lightweight competitor intelligence retrieval system powered by FastAPI and DashVector.**

[Features](#features) • [Quick Start](#quick-start) • [API Reference](#api-reference) • [Architecture](#architecture)

</div>

---

## 🌟 Features

- **⚡ Async Batch Processing** – Parse competitor data in batches with SQL atomic replacement
- **🔍 Semantic Search** – Vector-based competitor retrieval using DashVector
- **📊 Index Management** – Real-time index status monitoring and build triggering  
- **🔌 Pluggable Design** – Mount as sub-application or run standalone
- **🛡️ Production Ready** – Structured logging, error handling, and health checks

---

## 🚀 Quick Start

### Environment Setup

```bash
# Required environment variables
export DASHVECTOR_API_KEY="your-api-key"
export DASHVECTOR_ENDPOINT="https://your-endpoint.cn-beijing.aliyuncs.com"
export DASHVECTOR_COLLECTION="competitor_products"

# Optional
export LOG_LEVEL="INFO"  # DEBUG, INFO, WARNING, ERROR
```

### Run Standalone

```bash
# Install dependencies
pip install -r requirements.txt

# Start server
uvicorn competitors_searcher.app:app --host 0.0.0.0 --port 9000 --reload
```

### Mount as Sub-application

```python
from fastapi import FastAPI
from competitors_searcher.app import app as competitors_app

main_app = FastAPI(title="Main Application")
main_app.mount("/competitors", competitors_app)

# Access via:
# - GET  /competitors/health
# - GET  /competitors/v1/index/status
# - POST /competitors/v1/index/build
# - POST /competitors/v1/search_competitors
```

---

## 📡 API Reference

### Health Check
```http
GET /health
```
Returns service health status.

### Index Management

#### Trigger Index Build
```http
POST /v1/index/build
Content-Type: application/json

{
  "batch_size": 1000,
  "force_rebuild": false
}
```
**Flow:** Parse batch → SQL Replace → Build DashVector Index

#### Get Index Status
```http
GET /v1/index/status
```
Returns latest metadata document from DashVector including:
- `last_updated`: ISO timestamp
- `total_vectors`: Vector count
- `collection_name`: Target collection

### Search

#### Competitor Retrieval
```http
POST /v1/search_competitors
Content-Type: application/json

{
  "query": "electric vehicle battery technology",
  "top_k": 10,
  "filters": {
    "industry": "automotive",
    "founded_year": {"$gte": 2020}
  }
}
```

---

## 🏗️ Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Data Source   │────▶│ Batch Parser │────▶│  SQL Database   │
│  (CSV/API/ETL)  │     │   (Async)    │     │  (Temp Storage) │
└─────────────────┘     └──────────────┘     └─────────────────┘
                                                      │
┌─────────────────┐     ┌──────────────┐             │
│  DashVector     │◀────│ Index Builder│◀────────────┘
│  (Vector Index) │     │   (Upsert)   │
└─────────────────┘     └──────────────┘
         │
         ▼
┌─────────────────┐
│  Search API     │
│ (Semantic +     │
│  Metadata)      │
└─────────────────┘
```

---

## ⚙️ Configuration

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `DASHVECTOR_API_KEY` | ✅ | DashVector access key | - |
| `DASHVECTOR_ENDPOINT` | ✅ | Cluster endpoint URL | - |
| `DASHVECTOR_COLLECTION` | ✅ | Collection name | `competitor_products` |
| `DB_CONNECTION_STRING` | ❌ | SQL database URI | `sqlite:///./competitors.db` |
| `BATCH_SIZE` | ❌ | Processing batch size | `1000` |
| `EMBEDDING_MODEL` | ❌ | Embedding model name | `text-embedding-v2` |

---

## 🧪 Testing

```bash
# Run unit tests
pytest tests/ -v

# Run integration tests (requires DashVector credentials)
pytest tests/integration/ -v --envfile .env.test
```

---

## 📦 Deployment

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["uvicorn", "competitors_searcher.app:app", "--host", "0.0.0.0", "--port", "9000"]
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: competitors-searcher
spec:
  replicas: 2
  template:
    spec:
      containers:
      - name: api
        image: competitors-searcher:latest
        env:
        - name: DASHVECTOR_API_KEY
          valueFrom:
            secretKeyRef:
              name: dashvector-secret
              key: api-key
```

---

<div align="center">

---

# 🎯 竞争对手搜索服务

**基于 FastAPI 和 DashVector 的轻量化竞品情报检索系统**

[功能特性](#功能特性) • [快速开始](#快速开始) • [接口文档](#接口文档) • [架构设计](#架构设计)

</div>

---

## 🌟 功能特性

- **⚡ 异步批量处理** – 批量解析竞品数据，SQL 原子替换写入
- **🔍 语义检索** – 基于 DashVector 的向量相似度搜索
- **📊 索引管理** – 实时索引状态监控与构建触发
- **🔌 可插拔设计** – 支持独立运行或作为子应用挂载
- **🛡️ 生产就绪** – 结构化日志、异常处理与健康检查

---

## 🚀 快速开始

### 环境配置

```bash
# 必需环境变量
export DASHVECTOR_API_KEY="your-api-key"
export DASHVECTOR_ENDPOINT="https://your-endpoint.cn-beijing.aliyuncs.com"
export DASHVECTOR_COLLECTION="competitor_products"

# 可选配置
export LOG_LEVEL="INFO"  # DEBUG, INFO, WARNING, ERROR
```

### 独立运行

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
uvicorn competitors_searcher.app:app --host 0.0.0.0 --port 9000 --reload
```

### 作为子应用挂载

```python
from fastapi import FastAPI
from competitors_searcher.app import app as competitors_app

main_app = FastAPI(title="主应用")
main_app.mount("/competitors", competitors_app)

# 访问路径：
# - GET  /competitors/health          # 健康检查
# - GET  /competitors/v1/index/status # 索引状态
# - POST /competitors/v1/index/build  # 触发构建
# - POST /competitors/v1/search_competitors  # 竞品检索
```

---

## 📡 接口文档

### 健康检查
```http
GET /health
```
返回服务健康状态。

### 索引管理

#### 触发索引构建
```http
POST /v1/index/build
Content-Type: application/json

{
  "batch_size": 1000,      # 每批处理数量
  "force_rebuild": false   # 是否强制重建
}
```
**处理流程：** 批量解析 → SQL 原子替换 → 构建 DashVector 索引

#### 获取索引状态
```http
GET /v1/index/status
```
返回 DashVector 最新元数据文档，包含：
- `last_updated`: ISO 格式时间戳
- `total_vectors`: 向量总数
- `collection_name`: 集合名称

### 搜索接口

#### 竞品检索
```http
POST /v1/search_competitors
Content-Type: application/json

{
  "query": "新能源汽车电池技术",
  "top_k": 10,
  "filters": {
    "industry": "automotive",
    "founded_year": {"$gte": 2020}
  }
}
```

---

## 🏗️ 架构设计

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│     数据源      │────▶│   批量解析    │────▶│   SQL 数据库    │
│ (CSV/API/ETL)   │     │   (异步)      │     │   (临时存储)    │
└─────────────────┘     └──────────────┘     └─────────────────┘
                                                      │
┌─────────────────┐     ┌──────────────┐             │
│   DashVector    │◀────│   索引构建    │◀────────────┘
│   (向量数据库)   │     │   (Upsert)   │
└─────────────────┘     └──────────────┘
         │
         ▼
┌─────────────────┐
│    搜索 API     │
│  (语义+元数据)   │
└─────────────────┘
```

---

## ⚙️ 配置说明

| 环境变量 | 必需 | 说明 | 默认值 |
|----------|------|------|--------|
| `DASHVECTOR_API_KEY` | ✅ | DashVector 访问密钥 | - |
| `DASHVECTOR_ENDPOINT` | ✅ | 集群端点地址 | - |
| `DASHVECTOR_COLLECTION` | ✅ | 集合名称 | `competitor_products` |
| `DB_CONNECTION_STRING` | ❌ | SQL 数据库连接串 | `sqlite:///./competitors.db` |
| `BATCH_SIZE` | ❌ | 批处理大小 | `1000` |
| `EMBEDDING_MODEL` | ❌ | 嵌入模型名称 | `text-embedding-v2` |

---

## 🧪 测试

```bash
# 运行单元测试
pytest tests/ -v

# 运行集成测试（需要 DashVector 凭证）
pytest tests/integration/ -v --envfile .env.test
```

---

## 📦 部署指南

### Docker 部署

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["uvicorn", "competitors_searcher.app:app", "--host", "0.0.0.0", "--port", "9000"]
```

### Kubernetes 部署

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: competitors-searcher
spec:
  replicas: 2
  template:
    spec:
      containers:
      - name: api
        image: competitors-searcher:latest
        env:
        - name: DASHVECTOR_API_KEY
          valueFrom:
            secretKeyRef:
              name: dashvector-secret
              key: api-key
```

---

## 📄 License

MIT License © 2026
```