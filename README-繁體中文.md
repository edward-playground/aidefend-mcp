[English](README.md) | [繁體中文](README-繁體中文.md)

---

# AIDEFEND MCP Service

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109.2-009688.svg)](https://fastapi.tiangolo.com)
[![Security: Multiple Layers](https://img.shields.io/badge/security-multi--layer-success.svg)](./SECURITY.md)

一個為 [AIDEFEND framework](https://github.com/edward-playground/aidefend-framework) 打造的**本地端、去中心化 RAG (Retrieval-Augmented Generation) 引擎**。此服務提供安全且私密的方式存取 AIDEFEND AI 安全知識庫，所有敏感查詢都不會傳送到外部服務。

## 特色功能

- **100% 隱私保護與本地化**: 所有查詢都在本地端處理 - 你的 prompts 絕不會離開你的基礎設施，完全支援離線運作
- **成本效益高**: 相較於傳送完整 framework，token 用量減少 25 倍 - 大幅降低 LLM API 成本
- **自動同步**: 自動從 GitHub 拉取最新的 AIDEFEND 內容（每小時檢查一次）
- **快速向量搜尋**: 採用 LanceDB 實現高效的語意搜尋（毫秒級回應時間）
- **安全優先**: 全面的輸入驗證、清理與安全標頭
- **Docker 就緒**: 可輕鬆透過 Docker 和 docker-compose 部署
- **生產環境就緒**: 包含健康檢查、流量限制、結構化日誌與監控
- **深度防禦**: 多層安全機制（詳見 [SECURITY.md](./SECURITY.md)）

## 為什麼要使用這個 MCP Service？

AIDEFEND 是開源的，所以技術上你*可以*自己建立。但在「可能」和「實際」之間有很大的落差。

### 解決的問題

#### **問題 1: 雲端服務的隱私疑慮**

大多數 RAG 服務會將你的查詢傳送到雲端伺服器。你的敏感 prompts（安全問題、專有資訊）離開了你的掌控。

**這個 MCP Service：**
- ✅ **100% 本地端處理** - 查詢絕不離開你的機器
- ✅ **支援離線運作** - 初次同步後可完全離線
- ✅ **零追蹤** - 沒有遙測、沒有外部 API 呼叫

#### **問題 2: LLM 無法處理完整的 Framework**

AIDEFEND 有數千行程式碼。LLM 有 token 限制（~8K-128K）。你無法把所有東西貼進 ChatGPT。

**這個 MCP Service：**
- ✅ **智慧搜尋** - 在毫秒內找出 3-5 個最相關的段落
- ✅ **只傳送你需要的** - 不需要手動複製貼上

#### **問題 3: 建立 RAG 系統很複雜**

要自己建立，你需要：
- 撰寫 JavaScript parser
- 設定 vector database（LanceDB、ChromaDB、Pinecone）
- 配置 embedding models
- 手動處理更新（`git pull` → 重新解析 → 重新 embedding）

**這個 MCP Service：**
- ✅ **一行指令**: `docker-compose up -d`
- ✅ **每小時自動更新**
- ✅ **零維護** 需求

#### **問題 4: Token 成本快速累積**

傳送完整 framework = 每次查詢 50K+ tokens。付費 LLM API 按 token 計費。

**這個 MCP Service：**
- ✅ **每次查詢 500-2K tokens**（減少 25 倍）
- ✅ **付費 LLM API 成本降低 25 倍**（GPT-4、Claude）
- ✅ **更快的回應** - 更小的 context = 更快的處理

### 快速比較

| 功能 | DIY 自建 | Cloud RAG | 本 Service |
|---------|-----------|-----------|--------------|
| **隱私保護** | 本地端（如果你建得出來） | ❌ 雲端架構 | ✅ 100% 本地端 |
| **離線運作** | ❌ 否 | ❌ 否 | ✅ 是 |
| **每次查詢的 Token 用量** | 50K+（浪費） | 高 | ✅ 500-2K（減少 25 倍）|
| **安裝時間** | 數天 | 數分鐘 | ✅ 5 分鐘 |
| **自動更新** | ❌ 手動 | ✅ 是（雲端） | ✅ 是（本地端）|
| **維護** | 高成本 | 廠商管理 | ✅ 零成本 |
| **費用** | 你的時間 | $$/月訂閱 | ✅ $0 |

### 總結

取得一個生產環境就緒的 RAG 系統：
- **保護隱私** - 100% 本地端處理
- **省錢** - token 減少 25 倍 = API 成本降低 25 倍
- **離線運作** - 設定後無需網路
- **自動更新** - 永遠是最新研究
- **完全免費** - 開源無訂閱費

> **AIDEFEND framework 是知識。此服務以私密且高效的方式傳遞知識。**

## 架構

```
┌─────────────────────────────────────────────────────────────┐
│                    AIDEFEND MCP Service                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐         ┌──────────────┐                │
│  │              │         │              │                 │
│  │  Sync        │────────▶│  LanceDB     │                 │
│  │  Service     │  Index  │  Vector DB   │                 │
│  │              │         │              │                 │
│  └──────┬───────┘         └───────▲──────┘                 │
│         │                         │                         │
│         │ GitHub                  │ Query                   │
│         │ API                     │                         │
│         ▼                         │                         │
│  ┌──────────────┐         ┌──────┴──────┐                 │
│  │  AIDEFEND    │         │  Query      │                  │
│  │  Framework   │         │  Engine     │                  │
│  │  (GitHub)    │         │             │                  │
│  └──────────────┘         └──────▲──────┘                  │
│                                   │                         │
│                           ┌───────┴────────┐               │
│                           │   FastAPI      │               │
│                           │   REST API     │               │
│                           └───────▲────────┘               │
│                                   │                         │
└───────────────────────────────────┼─────────────────────────┘
                                    │
                            ┌───────┴────────┐
                            │  Your LLM      │
                            │  Application   │
                            └────────────────┘
```

## 前置需求

- **Python 3.9+**
- **Node.js**（用於解析 AIDEFEND JavaScript 檔案）
- **Docker**（選配，用於容器化部署）
- **4GB RAM** 最低需求（建議 8GB）
- **2GB 磁碟空間** 用於 models 和資料

## 快速開始

### 選項 1: 本地端安裝

1. **Clone repository**
   ```bash
   git clone https://github.com/edward-playground/aidefend-mcp.git
   cd aidefend-mcp
   ```

2. **安裝相依套件**
   ```bash
   pip install -r requirements.txt
   ```

3. **設定環境變數**
   ```bash
   cp .env.example .env
   # 如有需要請編輯 .env
   ```

4. **確認 Node.js 已安裝**
   ```bash
   node --version
   ```

5. **執行服務**
   ```bash
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

6. **檢查狀態**
   ```bash
   curl http://localhost:8000/health
   ```

服務會自動：
- 從 GitHub 下載 AIDEFEND framework 檔案
- 解析並索引內容
- 啟動 API server

存取 API 文件：http://localhost:8000/docs

### 選項 2: Docker 部署

1. **使用 docker-compose 建立並執行**
   ```bash
   docker-compose up -d
   ```

2. **檢查日誌**
   ```bash
   docker-compose logs -f
   ```

3. **檢查狀態**
   ```bash
   curl http://localhost:8000/health
   ```

## API 使用方式

### Query Endpoint

```bash
POST /api/v1/query
Content-Type: application/json

{
  "query_text": "如何防護 prompt injection 攻擊？",
  "top_k": 5
}
```

**使用 curl 的範例：**
```bash
curl -X POST "http://localhost:8000/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query_text": "AI 模型強化的最佳實踐是什麼？",
    "top_k": 5
  }'
```

**範例回應：**
```json
{
  "query_text": "AI 模型強化的最佳實踐是什麼？",
  "context_chunks": [
    {
      "source_id": "AID-H-001.001",
      "tactic": "Harden",
      "text": "Sub-Technique: Input Validation\nDescription: Implement robust input validation...",
      "metadata": {
        "type": "subtechnique",
        "name": "Input Validation",
        "pillar": "app",
        "phase": "building"
      },
      "score": 0.234
    }
  ],
  "total_results": 5,
  "timestamp": "2025-11-09T10:30:00Z"
}
```

### Status Endpoint

```bash
GET /api/v1/status
```

回傳服務狀態、同步資訊與版本細節。

### Health Check

```bash
GET /health
```

回傳所有元件的健康狀態（database、embedding model、sync service）。

### 手動觸發同步

```bash
POST /api/v1/sync
```

手動觸發同步操作（流量限制為每分鐘 5 次）。

## 設定

所有設定都透過環境變數完成。請參閱 [.env.example](./.env.example) 檢視所有選項。

### 主要設定選項

| 變數 | 預設值 | 說明 |
|----------|---------|-------------|
| `SYNC_INTERVAL_SECONDS` | `3600` | 檢查更新的頻率（1 小時）|
| `API_PORT` | `8000` | API server 執行的 port |
| `LOG_LEVEL` | `INFO` | 日誌等級（DEBUG、INFO、WARNING、ERROR）|
| `ENABLE_RATE_LIMITING` | `true` | 在 API endpoints 啟用流量限制 |
| `RATE_LIMIT_PER_MINUTE` | `60` | 每個 IP 每分鐘的最大請求數 |
| `MAX_QUERY_LENGTH` | `2000` | 查詢文字的最大長度 |
| `NODE_EXECUTABLE` | `node` | Node.js 執行檔的路徑 |

## 安全性

作為 AI 安全 framework 的 MCP service，本服務實作了多層安全機制：

- **本地優先處理**: 所有查詢都在本地端處理 - 你的資料絕不離開你的基礎設施
- **輸入驗證**: 全面的驗證與清理所有輸入
- **流量限制**: 防護濫用與 DoS 攻擊
- **安全操作**: 路徑遍歷防護、檔案安全與權限控制
- **網路安全**: SSRF 防護、URL 驗證與安全標頭
- **容器強化**: 非 root 使用者、最小權限與安全預設值
- **稽核日誌**: 結構化日誌並自動過濾敏感資料

**關於安全問題、漏洞回報與部署最佳實踐，請參閱 [SECURITY.md](./SECURITY.md)。**

## 監控與日誌

### 結構化日誌

日誌以 JSON 格式寫入 `./data/logs/aidefend_mcp.log`：

```json
{
  "timestamp": "2025-11-09T10:30:00Z",
  "level": "INFO",
  "logger": "aidefend_mcp",
  "message": "Query completed",
  "module": "core",
  "function": "search",
  "extra": {
    "results_returned": 5,
    "top_score": 0.234
  }
}
```

### 健康監控

`/health` endpoint 提供元件級的健康檢查：

```bash
curl http://localhost:8000/health
```

## 開發

### 設定開發環境

```bash
# 安裝開發用相依套件
pip install -r requirements-dev.txt

# 執行測試
pytest

# 檢查程式碼品質
black app/
flake8 app/
mypy app/

# 安全掃描
safety check
bandit -r app/
```

### 專案結構

```
aidefend-mcp/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI application
│   ├── config.py        # Configuration management
│   ├── core.py          # Query engine
│   ├── sync.py          # GitHub sync service
│   ├── schemas.py       # Pydantic models
│   ├── security.py      # Security validations
│   ├── logger.py        # Structured logging
│   └── utils.py         # Utility functions
├── data/                # Auto-generated data directory
│   ├── raw_content/     # Downloaded .js files
│   ├── aidefend_kb.lancedb/  # Vector database
│   ├── local_version.json    # Sync version info
│   └── logs/            # Log files
├── tests/               # Test suite
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── README.md
└── SECURITY.md
```

## 疑難排解

### 服務無法啟動

1. **檢查 Node.js 是否已安裝**
   ```bash
   node --version
   ```

2. **檢查日誌**
   ```bash
   tail -f data/logs/aidefend_mcp.log
   ```

3. **確認可存取 GitHub**
   ```bash
   curl https://api.github.com/repos/edward-playground/aidefend-framework/commits/main
   ```

### 查詢回傳 "Service not ready"

- 初次同步仍在進行中。請透過 `/api/v1/status` 檢查同步狀態。
- database 可能損毀。刪除 `data/` 目錄並重新啟動服務。

### 流量限制問題

在 `.env` 調整 `RATE_LIMIT_PER_MINUTE` 或用 `ENABLE_RATE_LIMITING=false` 停用。

## 貢獻

歡迎貢獻！請：

1. Fork repository
2. 建立 feature branch
3. 執行測試與安全檢查
4. 提交 pull request

## 授權

本專案採用 MIT License - 詳見 [LICENSE](LICENSE) 檔案。

Copyright (c) 2025 Edward Lee (edward-playground)

## 致謝

- [AIDEFEND Framework](https://github.com/edward-playground/aidefend-framework) - AI 安全知識庫
- [LanceDB](https://lancedb.com/) - 快速 vector database
- [FastAPI](https://fastapi.tiangolo.com/) - 現代化 Python web framework
- [Sentence Transformers](https://www.sbert.net/) - Embedding models

## 作者

**Edward Lee**
- GitHub: [@edward-playground](https://github.com/edward-playground)
- LinkedIn: [Edward Lee](https://www.linkedin.com/in/go-edwardlee/)

## 支援

關於問題與提問：
- GitHub Issues: [建立 issue](https://github.com/edward-playground/aidefend-mcp/issues)
- 安全問題: 請參閱 [SECURITY.md](./SECURITY.md)

---

**用 ❤️ 為 AI 安全社群打造**
