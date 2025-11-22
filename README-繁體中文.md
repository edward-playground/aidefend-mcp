[English Readme](README.md) | [繁體中文 Readme](README-繁體中文.md)

---

# AIDEFEND MCP / REST API Service

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%20|%203.13-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.121.1-009688.svg)](https://fastapi.tiangolo.com)
[![Security: Multiple Layers](https://img.shields.io/badge/security-multi--layer-success.svg)](./SECURITY.md)

一個為 [AIDEFEND framework](https://github.com/edward-playground/aidefense-framework) 打造的**本地端、去中心化 RAG (Retrieval-Augmented Generation) 引擎服務**。此服務提供安全、隱私的 AIDEFEND 知識庫存取，不會將敏感查詢傳送到外部服務。支援兩種模式：

- **REST API**：適用於自訂應用程式與系統整合。

- **MCP Server**：適用於與 AI 助理（如 Claude Desktop）的原生整合。

## 特色功能

- **100% 隱私保護與本地化**：所有查詢都在本地端處理 - 你的 prompts 只留在你的環境裡，完全支援離線運作
- **多語言支援**：使用任何語言（中文、日文、韓文等）查詢，都能取得相關的英文內容結果，採用 `intfloat/multilingual-e5-base`（Microsoft，支援 100+ 語言）
- **成本效益高**：相較於傳送完整 framework，token 用量減少 25 倍 - 大幅降低 LLM API 成本
- **長查詢支援**：自動分塊處理長查詢（最長 5000 字元），聰明地保留句子邊界
- **自動同步**：自動從 GitHub 下載最新的 AIDEFEND 內容（預設是每小時檢查一次）
- **快速向量搜尋**：LanceDB 驅動的語意搜尋（CPU：單次查詢 500-1000ms；可選 GPU 加速：100-300ms - 參見 [GPU 指南](docs/advanced/GPU_ACCELERATION.md)）
- **安全優先**：全面的輸入驗證、清理與安全 Header
- **Docker 環境適用**：可輕鬆透過 Docker 和 docker-compose 部署
- **Prod 環境適用**：包含健康檢查、流量限制、結構化日誌與監控
- **深度防禦**：多層安全機制（詳見 [SECURITY.md](./SECURITY.md)）

## 為什麼要使用這個 MCP / REST API Service？

AIDEFEND 是開源的，所以理論上呢，你可以自己去 AIDEFEND 的 GitHub Repo 抓取 AIDEFEND 的資料來用。但從實際面的角度，有以下的問題：

### 此服務解決的問題

#### **問題 1：雲端服務的隱私疑慮**

如果你使用雲端 RAG 服務的話，大多數 RAG 服務會將你的查詢傳送到雲端伺服器。你的敏感 prompts（安全問題、機敏資訊）有洩漏的可能。

**這個 MCP / REST API Service：**
- ✅ **100% 本地端處理** - 本地查詢
- ✅ **支援離線運作** - 初次同步後可完全離線
- ✅ **零追蹤** - 沒有遙測、沒有外部 API 呼叫

#### **問題 2：LLM 無法處理完整的 AIDEFEND Framework**

AIDEFEND 的防禦手法（Techniques / Sub-Techniques / Strategies）有數千行程式碼。蠻多 LLM 服務有 context window 限制（~8K-128K）。把所有東西貼進 LLM 服務（ChatGPT/Claude/Gemini/Grok, etc）有時候會遇到困難。

**這個 MCP / REST API Service：**
- ✅ **智慧搜尋** - 在毫秒內找出 3-5 個最相關的段落
- ✅ **只傳送你需要的** - 不需要手動複製貼上

#### **問題 3：建立 RAG 系統很複雜**

如果你選擇要自己建立 RAG 功能，你需要：
- 撰寫 JavaScript parser
- 設定 vector database（LanceDB、ChromaDB、Pinecone）
- 配置 embedding models
- 手動處理更新（`git pull` → 重新解析 → 重新 embedding）

**這個 MCP / REST API Service：**
- ✅ **一行指令**：`docker-compose up -d`
- ✅ **每小時自動更新**
- ✅ **零維護成本**

#### **問題 4：Token 成本快速累積**

傳送完整的 AIDEFEND framework = 每次查詢 50K+ tokens。付費 LLM API 是按 token 計費的。

**這個 MCP / REST API Service：**
- ✅ **每次查詢 500-2K tokens**（減少 25 倍）
- ✅ **付費 LLM API 成本降低 25 倍**（GPT-4、Claude）
- ✅ **更快的回應** - 較小的 context = 更快的處理

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

> **AIDEFEND framework 是 AI 系統防禦知識庫。而這個 AIDEFEND MCP 服務，讓你能用安全且高效的方式來查詢和利用 AIDEFEND 裡的知識。**

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
│  │  (GitHub)    │         │  (共享)     │     │              │
│  └──────────────┘         └──────┬──────┘     │             │
│                                   │           │             │
│                          ┌────────┴────────┐  │             │
│                          │                 │  │             │
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

- **Python 3.9 - 3.13**（已在 3.13.6 上測試）
- **Node.js 18+**（解析 JavaScript 文件時必需）
  - 下載：https://nodejs.org/
  - 驗證：`node --version`
- **Docker**（選配，用於容器化部署）
- **2GB RAM** 最低需求（建議 4GB）
- **500MB 磁碟空間** 用於 models 和資料

## 快速開始

### 步驟 1：安裝（兩種模式共用）

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

### 步驟 2：選擇你的模式

#### 選項 A：REST API 模式（用於 HTTP 整合）

**何時使用：** 你想要與自訂應用程式、腳本或任何 HTTP 客戶端整合。

1. **啟動服務**

   **使用便利腳本：**
   ```bash
   # 在 macOS/Linux 上：
   ./scripts/start.sh

   # 在 Windows 上：
   scripts\start.bat
   ```

   **或直接用 Python 啟動：**
   ```bash
   # 預設（REST API 模式）
   C:/Python313/python.exe __main__.py

   # 或明確指定 REST API 模式
   C:/Python313/python.exe __main__.py --api
   ```

2. **驗證是否正在執行**
   ```bash
   curl http://localhost:8000/health
   ```

3. **存取 API 文件**

   開啟瀏覽器：http://localhost:8000/docs

服務會在首次執行時自動與 GitHub 同步並索引 AIDEFEND framework。

#### 選項 B：MCP 模式（用於 Claude Desktop）

**何時使用：** 你想讓 Claude Desktop 直接作為工具存取 AIDEFEND 知識庫。

1. **設定 Claude Desktop**

   編輯 Claude Desktop 的設定檔：
   - **macOS：** `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows：** `%APPDATA%\Claude\claude_desktop_config.json`

      - (在大部分的 Windows 機器上，這個位置可能在：C:\Users\\[您的使用者名稱]\AppData\Roaming\Claude\\)

   加入此設定：
   ```json
   {
     "mcpServers": {
       "aidefend": {
         "command": "C:/Python313/python.exe",
         "args": [
           "/absolute/path/to/aidefend-mcp/__main__.py",
           "--mcp"
         ],
         "cwd": "/absolute/path/to/aidefend-mcp"
       }
     }
   }
   ```

   **⚠️ 重要：** 將所有路徑替換為**您實際的絕對路徑**！

   1. **Python 執行檔路徑**（在 `command` 欄位中）：
      - 將 `C:/Python313/python.exe` 替換為您實際的 Python 安裝路徑
      - 如何找到您的 Python 路徑：
        - Windows：在命令提示字元執行 `where python`
        - macOS/Linux：在終端機執行 `which python` 或 `which python3`
      - 常見位置：
        - Windows：`C:/Python313/python.exe`、`C:/Python312/python.exe`、`C:/Users/YourName/AppData/Local/Programs/Python/Python313/python.exe`
        - macOS：`/usr/local/bin/python3`、`/opt/homebrew/bin/python3`
        - Linux：`/usr/bin/python3`、`/usr/local/bin/python3`

   2. **專案路徑**（在 `args` 和 `cwd` 欄位中）：
      - 替換 `/absolute/path/to/aidefend-mcp/__main__.py` 在 `args` 欄位中
      - 替換 `/absolute/path/to/aidefend-mcp` 在 `cwd` 欄位中
      - `cwd` 欄位是必要的，這樣 Python 才能正確解析專案內的相對匯入

   **完整範例：**
   - Windows：
     - `"command": "C:/Python313/python.exe"`
     - `"args": ["C:/Users/YourName/projects/aidefend-mcp/__main__.py", "--mcp"]`
     - `"cwd": "C:/Users/YourName/projects/aidefend-mcp"`
   - macOS/Linux：
     - `"command": "/usr/local/bin/python3"`
     - `"args": ["/Users/yourname/projects/aidefend-mcp/__main__.py", "--mcp"]`
     - `"cwd": "/Users/yourname/projects/aidefend-mcp"`

2. **重新啟動 Claude Desktop**

   完全關閉並重新開啟 Claude Desktop 應用程式。

3. **驗證連線**

   在 Claude Desktop 中，你應該會在 MCP 工具清單中看到「aidefend」（尋找 🔌 圖示）。試著詢問：
   ```
   「可以搜尋 AIDEFEND 中關於 prompt injection 的防禦手法嗎？」
   ```

   Claude 會自動使用 `query_aidefend` 工具來搜尋知識庫。

**詳細的 MCP 設定說明，請參閱 [INSTALL-繁體中文.md](INSTALL-繁體中文.md)。**

#### 選項 C：Docker 部署（REST API 模式）

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

## 使用方式

> **💡 提示：** 疑難排解和維護指令（包含資料庫重新同步）請參閱 [INSTALL.md 的疑難排解章節](INSTALL.md#troubleshooting)。

### REST API 模式使用方式

REST API 提供 HTTP 端點，可與任何應用程式整合。

#### Query Endpoint

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

#### 其他關鍵端點

```bash
# 服務狀態
GET /api/v1/status

# 健康檢查
GET /health

# 手動同步
POST /api/v1/sync
```

> **📖 完整 API 文件：** http://localhost:8000/docs（當服務執行時）

### MCP 模式使用方式

以 MCP 模式執行時（`python __main__.py --mcp`），本服務會為 AI 助理（如 Claude Desktop）提供工具。

**對話範例：**

```
你：「如何防禦 prompt injection 攻擊？」

Claude：[自動使用 query_aidefend 工具]
       根據 AIDEFEND framework，以下是主要的防禦手法...
```

> **📖 完整 MCP 工具參考：** [docs/TOOLS-繁體中文.md](docs/TOOLS-繁體中文.md)

## 可用工具（19 個工具）

AIDEFEND MCP Service 提供 **19 個專業工具**，用於 AI 安全分析：

### 基礎查詢工具（4 個工具）
- 🔍 **query_aidefend** - 搜尋 AIDEFEND 知識庫
- ✅ **get_aidefend_status** - 檢查服務狀態
- 🔄 **sync_aidefend** - 手動觸發同步
- 📦 **get_framework_version** - 取得 framework 版本

### 技術分析工具（4 個工具）
- 📊 **get_statistics** - 知識庫統計資訊
- ✅ **validate_technique_id** - 驗證技術 ID
- 📖 **get_technique_detail** - 深入了解技術
- 💻 **get_secure_code_snippet** - 取得程式碼範例

### 威脅分析工具（3 個工具）
- 🛡️ **get_defenses_for_threat** - 尋找威脅的防禦手法
- 🎯 **classify_threat** - 威脅分類（100% 本地）
- 📋 **get_threat_coverage** - 分析威脅涵蓋範圍

### 規劃與分析工具（5 個工具）
- 📈 **analyze_coverage** - 找出防禦缺口
- 🗺️ **map_to_compliance_framework** - 對應到合規（NIST、EU AI Act 等）
- ⚖️ **compare_techniques** - 並排比較技術
- 🎯 **get_implementation_plan** - 取得優先順序建議
- 🛡️ **analyze_security_posture** - 全面的安全態勢分析

### 進階工具（3 個工具）
- 🔎 **comprehensive_search** - 多查詢聚合搜尋
- 📝 **get_quick_reference** - 產生檢查清單
- 🚨 **generate_incident_playbook** - 事件應變手冊

> **📖 完整工具文檔與範例：** [docs/TOOLS-繁體中文.md](docs/TOOLS-繁體中文.md)

## 設定

所有設定都透過環境變數完成。複製 `.env.example` 到 `.env` 並依需求自訂。

### 主要設定選項

```bash
# 驗證
AUTH_MODE=no_auth                    # 或 "api_key" 用於生產環境
AIDEFEND_API_KEY=<your-key>          # AUTH_MODE=api_key 時必需

# 伺服器
API_HOST=127.0.0.1                   # 使用 0.0.0.0 以允許外部存取
API_PORT=8000
API_WORKERS=1                        # ⚠️ 必須為 1（不支援多 worker）

# 同步
SYNC_INTERVAL_SECONDS=3600           # 自動同步頻率（1 小時）

# Embedding
EMBEDDING_MODEL=intfloat/multilingual-e5-base
EMBEDDING_DIMENSION=768

# 流量限制
ENABLE_RATE_LIMITING=true
RATE_LIMIT_PER_MINUTE=60
```

> **📖 完整設定指南：** [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

## 安全

作為 AI 安全 framework 的 MCP 服務，本服務實作了多層安全機制：

- **本地優先處理**：所有查詢在本地處理
- **輸入驗證**：全面的清理
- **流量限制**：DoS 保護
- **驗證**：選配的 API key 驗證
- **容器強化**：非 root 使用者、最小權限
- **稽核日誌**：結構化日誌與敏感資料過濾

> **📖 安全政策與最佳實踐：** [SECURITY.md](./SECURITY.md)

## 疑難排解

**常見問題：**

- **服務無法啟動：** 檢查 logs：`data/logs/aidefend_mcp.log`
- **資料庫錯誤：** 執行 `python __main__.py --resync`
- **MCP 工具未顯示：** 驗證 Claude Desktop config 中的絕對路徑
- **查詢緩慢：** 初次同步進行中，請等待完成

> **📖 完整疑難排解指南：** [INSTALL.md#troubleshooting](INSTALL.md#troubleshooting)

## 開發

想要貢獻？太好了！

```bash
# 安裝開發相依套件
pip install -r requirements-dev.txt

# 執行測試
pytest

# 檢查程式碼品質
black app/
flake8 app/
mypy app/
```

> **📖 開發指南：** [CONTRIBUTING.md](CONTRIBUTING.md)

## 專案結構

```
aidefend-mcp/
├── __main__.py              # 進入點（模式選擇）
├── mcp_server.py            # MCP 協定伺服器
├── app/
│   ├── main.py              # FastAPI REST API
│   ├── core.py              # QueryEngine（共享）
│   ├── sync.py              # 背景同步
│   └── tools/               # 19 個專業工具
├── docs/                    # 文件
│   ├── TOOLS-繁體中文.md    # 完整工具參考
│   └── CONFIGURATION.md     # 設定指南
├── tests/                   # 測試套件
└── data/                    # 執行時資料
```

## 授權

本專案採用 MIT 授權 - 詳見 [LICENSE](LICENSE) 檔案。

## 致謝

- **AIDEFEND Framework**：[edward-playground/aidefense-framework](https://github.com/edward-playground/aidefense-framework)
- **FastAPI**：現代 Python 網頁框架
- **LanceDB**：語意搜尋用的向量資料庫
- **FastEmbed**：基於 ONNX 的 embedding 模型
- **Anthropic MCP**：Model Context Protocol

---

**有問題或議題？** 請在 [GitHub](https://github.com/edward-playground/aidefend-mcp/issues) 開啟 issue。
