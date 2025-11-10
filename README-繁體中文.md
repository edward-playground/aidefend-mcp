[English Readme](README.md) | [繁體中文 Readme](README-繁體中文.md)

---

# AIDEFEND MCP Service

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109.2-009688.svg)](https://fastapi.tiangolo.com)
[![Security: Multiple Layers](https://img.shields.io/badge/security-multi--layer-success.svg)](./SECURITY.md)

一個為 [AIDEFEND framework](https://github.com/edward-playground/aidefense-framework) 打造的**本地端、去中心化 RAG (Retrieval-Augmented Generation) 引擎**。此服務提供安全且私密的方式存取 AIDEFEND AI 安全知識庫，所有敏感查詢都不會傳送到外部服務。

## 特色功能

- **100% 隱私保護與本地化**: 所有查詢都在本地端處理 - 你的 prompts 絕不會離開你的基礎設施，完全支援離線運作
- **成本效益高**: 相較於傳送完整 framework，token 用量減少 25 倍 - 大幅降低 LLM API 成本
- **自動同步**: 自動從 GitHub 下載最新的 AIDEFEND 內容（每小時檢查一次）
- **快速向量搜尋**: 採用 LanceDB 實現快速的語意搜尋（毫秒級回應時間）
- **安全優先**: 全面的輸入驗證、清理與安全Header
- **Docker環境適用**: 可輕鬆透過 Docker 和 docker-compose 部署
- **Prod環境適用**: 包含健康檢查、流量限制、結構化日誌與監控
- **深度防禦**: 多層安全機制（詳見 [SECURITY.md](./SECURITY.md)）

## 為什麼要使用這個 MCP Service？

AIDEFEND 是開源的，所以技術上你*可以*自己建立一些服務，去 AIDEFEND 的 GitHub Repo 抓取 AIDEFEND 的資料並加以查詢使用。但在「可以」和「實際」之間有一些落差:

### 問題

#### **問題 1: 雲端服務的隱私疑慮**

大多數 RAG 服務會將你的查詢傳送到雲端伺服器。你的敏感 prompts（安全問題、機敏資訊）離開了你的掌控。

**這個 MCP Service：**
- ✅ **100% 本地端處理** - 查詢絕不離開你的機器
- ✅ **支援離線運作** - 初次同步後可完全離線
- ✅ **零追蹤** - 沒有遙測、沒有外部 API 呼叫

#### **問題 2: LLM 無法處理完整的 AIDEFEND Framework**

AIDEFEND 的防禦手法 (Techniques / Sub-Techniques / Strategies) 有數千行程式碼。蠻多 LLM 服務有 context window 限制（~8K-128K）。把所有東西貼進 LLM 服務 (ChatGPT/Claude/Gemini/Grok, etc) 有時候會遇到困難。

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

#### **問題 4: Token 成本快速累積**

傳送完整的 AIDEFEND framework = 每次查詢 50K+ tokens。付費 LLM API 按 token 計費。

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
- **自動更新** - 永遠同步最新的研究
- **完全免費** - 開源無訂閱費

> **AIDEFEND framework 是知識庫。而這個 AIDEFEND MCP 服務是用安全且高效的方式來讓你利用 AIDEFEND 這個知識。**

## 架構

### 雙模式設計

本服務支援**兩種模式**以適應不同使用情境：

1. **REST API 模式** - 用於系統整合（現有應用程式、自訂工具）
2. **MCP 模式** - 用於 AI 助理（Claude Desktop、其他 MCP 相容的客戶端）

兩種模式共享相同的核心邏輯，確保結果的一致性。

```
┌─────────────────────────────────────────────────────────────┐
│                    AIDEFEND MCP Service                     │
│                      （雙模式支援）                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐         ┌──────────────┐                  │
│  │              │         │              │                  │
│  │  Sync        │────────▶│  LanceDB     │                 │
│  │  Service     │  Index  │  Vector DB   │                  │
│  │              │         │              │                  │
│  └──────┬───────┘         └───────▲──────┘                  │
│         │                         │                         │
│         │ GitHub                  │ Query                   │
│         │ API                     │                         │
│         ▼                         │                         │
│  ┌──────────────┐         ┌──────┴──────┐                   │
│  │  AIDEFEND    │         │  Query      │                   │
│  │  Framework   │         │  Engine     │◀────┐             │
│  │  (GitHub)    │         │  (共享)     │     │             │
│  └──────────────┘         └──────┬──────┘     │             │
│                                   │            │             │
│                          ┌────────┴────────┐   │             │
│                          │                 │   │             │
│                    ┌─────▼──────┐   ┌──────▼─────┐          │
│                    │  FastAPI   │   │ MCP Server │          │
│                    │  REST API  │   │  (stdio)   │          │
│                    └─────┬──────┘   └──────┬─────┘          │
│                          │                 │                │
└──────────────────────────┼─────────────────┼────────────────┘
                           │                 │
                  ┌────────┴────────┐ ┌──────┴──────┐
                  │  你的 LLM       │ │   Claude    │
                  │  應用程式        │ │   Desktop   │
                  │  (HTTP 客戶端)  │ │   (MCP)     │
                  └─────────────────┘ └─────────────┘
```

### 何時使用各種模式

| 使用情境 | 建議模式 | 原因 |
|----------|------------------|-----|
| **Claude Desktop 整合** | MCP 模式 | 原生工具支援，不需要 HTTP |
| **自訂腳本/自動化** | REST API 模式 | 標準 HTTP，易於整合 |
| **系統整合** | REST API 模式 | 可與任何 HTTP 客戶端配合 |
| **AI 助理對話** | MCP 模式 | 為 AI 助理工作流程最佳化 |
| **同時使用兩者** | 同時執行兩個！ | 可在同一台機器上共存 |

## 前置需求

- **Python 3.9+**
- **Docker**（選配，用於容器化部署）
- **2GB RAM** 最低需求（建議 4GB）
- **500MB 磁碟空間** 用於 models 和資料

## 快速開始

### 步驟 1: 安裝（兩種模式共用）

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
   # 如有需要請編輯 .env（選配）
   ```

### 步驟 2: 選擇你的模式

#### 選項 A: REST API 模式（用於 HTTP 整合）

**何時使用：** 你想要與自訂應用程式、腳本或任何 HTTP 客戶端整合。

1. **啟動服務**
   ```bash
   python -m aidefend_mcp
   # 或等同於：
   # python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

2. **驗證是否正在執行**
   ```bash
   curl http://localhost:8000/health
   ```

3. **存取 API 文件**

   開啟瀏覽器：http://localhost:8000/docs

服務會在首次執行時自動與 GitHub 同步並索引 AIDEFEND framework。

#### 選項 B: MCP 模式（用於 Claude Desktop）

**何時使用：** 你想讓 Claude Desktop 直接作為工具存取 AIDEFEND 知識庫。

1. **設定 Claude Desktop**

   編輯 Claude Desktop 的設定檔：
   - **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

   加入此設定：
   ```json
   {
     "mcpServers": {
       "aidefend": {
         "command": "python",
         "args": [
           "-m",
           "aidefend_mcp",
           "--mcp"
         ],
         "cwd": "/absolute/path/to/aidefend-mcp"
       }
     }
   }
   ```

   **重要：** 將 `/absolute/path/to/aidefend-mcp` 替換為你的實際目錄路徑！

2. **重新啟動 Claude Desktop**

   完全關閉並重新開啟 Claude Desktop 應用程式。

3. **驗證連線**

   在 Claude Desktop 中，你應該會在 MCP 工具清單中看到「aidefend」（尋找 🔌 圖示）。試著詢問：
   ```
   "可以搜尋 AIDEFEND 中關於 prompt injection 的防禦手法嗎？"
   ```

   Claude 會自動使用 `query_aidefend` 工具來搜尋知識庫。

**詳細的 MCP 設定說明，請參閱 [INSTALL-繁體中文.md](INSTALL-繁體中文.md)。**

#### 選項 C: Docker 部署（REST API 模式）

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

**注意：** MCP 模式需要直接執行 Python，無法在 Docker 中運行（Claude Desktop 需要直接的 stdio 存取）。

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

---

### MCP 模式使用方式

當以 MCP 模式執行時（`python -m aidefend_mcp --mcp`），本服務會為 AI 助理（如 Claude Desktop）提供工具。

#### 可用的 MCP 工具

1. **query_aidefend** - 搜尋 AIDEFEND 知識庫
2. **get_aidefend_status** - 檢查服務狀態與同步資訊
3. **sync_aidefend** - 手動觸發知識庫同步

#### 如何在 Claude Desktop 中使用

設定完成後，當你詢問 AIDEFEND 相關問題時，Claude Desktop 可以自動使用這些工具。

**對話範例：**

```
你: "如何防禦 prompt injection 攻擊？"

Claude: [自動使用 query_aidefend 工具]
       根據 AIDEFEND framework，以下是主要的防禦手法...
```

```
你: "AIDEFEND 知識庫的狀態如何？"

Claude: [使用 get_aidefend_status 工具]
       AIDEFEND 服務已索引 42 份文件...
```

```
你: "可以同步最新的 AIDEFEND 戰術嗎？"

Claude: [使用 sync_aidefend 工具]
       正在與 GitHub 同步... 知識庫已成功更新！
```

#### 明確使用工具

你也可以要求 Claude 使用特定工具：

```
你: "使用 query_aidefend 工具搜尋『model poisoning defenses』"

Claude: [以你的確切查詢呼叫 query_aidefend]
```

#### MCP 工具結構描述

對於整合其他 MCP 客戶端的開發者，這裡是工具結構描述：

**query_aidefend:**
```json
{
  "name": "query_aidefend",
  "description": "搜尋 AIDEFEND AI 安全防禦知識庫...",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "以自然語言撰寫的搜尋查詢"
      },
      "top_k": {
        "type": "number",
        "description": "要回傳的結果數量（預設：5，最大：20）",
        "default": 5
      }
    },
    "required": ["query"]
  }
}
```

**get_aidefend_status:**
```json
{
  "name": "get_aidefend_status",
  "description": "取得 AIDEFEND 知識庫的目前狀態...",
  "inputSchema": {
    "type": "object",
    "properties": {},
    "required": []
  }
}
```

**sync_aidefend:**
```json
{
  "name": "sync_aidefend",
  "description": "手動觸發與 AIDEFEND GitHub repository 的同步...",
  "inputSchema": {
    "type": "object",
    "properties": {},
    "required": []
  }
}
```

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

## 安全性

作為 AI 安全 framework 的 MCP service，本服務實作了多層安全機制：

- **本地優先處理**: 所有查詢都在本地端處理 - 你的資料不會離開你的基礎設施範圍
- **輸入驗證**: 全面的驗證與清理所有輸入
- **流量限制**: 防止資源濫用與 DoS 攻擊
- **安全操作**: 路徑遍歷防護、檔案安全與權限控制
- **網路安全**: SSRF 防護、URL 驗證與安全標頭
- **容器強化**: 非 root 使用者、最小權限與安全預設值
- **稽核日誌**: 結構化日誌並自動過濾敏感資料

**關於資安相關資訊，請參閱 [SECURITY.md](./SECURITY.md)。**

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
├── __main__.py          # 統一入口點（模式選擇）
├── mcp_server.py        # MCP 協議 server 實作
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI application（REST API 模式）
│   ├── config.py        # 設定管理
│   ├── core.py          # Query engine（兩種模式共享）
│   ├── sync.py          # GitHub 同步服務
│   ├── schemas.py       # Pydantic models
│   ├── security.py      # 安全驗證
│   ├── logger.py        # 結構化日誌
│   └── utils.py         # 工具函式
├── data/                # 自動產生的資料目錄
│   ├── raw_content/     # 下載的 .js 檔案
│   ├── aidefend_kb.lancedb/  # Vector database
│   ├── local_version.json    # 同步版本資訊
│   └── logs/            # 日誌檔案
├── tests/               # 測試套件
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml       # 專案設定
├── .env.example
├── README.md
├── INSTALL.md           # 安裝指南
└── SECURITY.md
```

## 疑難排解

### 服務無法啟動

1. **檢查日誌**
   ```bash
   tail -f data/logs/aidefend_mcp.log
   ```

2. **確認可存取 GitHub**
   ```bash
   curl https://api.github.com/repos/edward-playground/aidefense-framework/commits/main
   ```

### 查詢回傳 "Service not ready"

- 初次同步仍在進行中。請透過 `/api/v1/status` 檢查同步狀態。
- database 可能損毀。刪除 `data/` 目錄並重新啟動服務。

### 流量限制問題

在 `.env` 調整 `RATE_LIMIT_PER_MINUTE` 或用 `ENABLE_RATE_LIMITING=false` 停用。

### MCP 模式問題

#### Claude Desktop 沒有顯示工具

1. **確認設定檔路徑**
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`

2. **檢查設定語法**
   - 必須是有效的 JSON（使用 JSON 驗證器）
   - 使用絕對路徑，而非相對路徑
   - 確保 `cwd` 指向正確的目錄

3. **重新啟動 Claude Desktop**
   - 完全退出並重新開啟應用程式
   - 檢查 Claude 控制台的錯誤訊息

4. **手動測試 MCP server**
   ```bash
   python -m aidefend_mcp --mcp
   ```
   - 你應該會在 stderr 看到「Waiting for MCP client connections...」
   - 如果當機，請檢查錯誤訊息

#### MCP 工具速度慢或逾時

- 首次查詢會觸發初始同步（1-3 分鐘）
- 檢查同步是否完成：`python -m aidefend_mcp` 然後造訪 http://localhost:8000/api/v1/status
- 初始同步後，查詢應該很快（< 1 秒）

#### "Database sync in progress" 錯誤

- 等待幾秒後重試
- 這是為了防止同步期間的 race condition
- 檢查同步錯誤日誌：`tail -f data/logs/aidefend_mcp.log`

## 授權

本專案採用 MIT License - 詳見 [LICENSE](LICENSE) 檔案。

Copyright (c) 2025 Edward Lee (edward-playground)

## 致謝

- [LanceDB](https://lancedb.com/) - 快速 vector database
- [FastAPI](https://fastapi.tiangolo.com/) - 現代化 Python web framework
- [FastEmbed](https://qdrant.github.io/fastembed/) - 輕量級 ONNX-based embedding models

## 作者

**Edward Lee**
- GitHub: [@edward-playground](https://github.com/edward-playground)
- LinkedIn: [Edward Lee](https://www.linkedin.com/in/go-edwardlee/)

## 支援

關於問題與提問：
- GitHub Issues: [建立 issue](https://github.com/edward-playground/aidefend-mcp/issues)
- 安全問題: 請參閱 [SECURITY.md](./SECURITY.md)


