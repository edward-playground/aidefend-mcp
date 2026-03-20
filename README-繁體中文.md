[English Readme](README.md) | [繁體中文 Readme](README-繁體中文.md)

---

# AIDEFEND MCP / REST API Service

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%20|%203.13-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.121.1-009688.svg)](https://fastapi.tiangolo.com)
[![Security: Multiple Layers](https://img.shields.io/badge/security-multi--layer-success.svg)](./SECURITY.md)

一個為 [AIDEFEND framework](https://github.com/edward-playground/aidefense-framework) 打造的**本地端、去中心化 RAG (Retrieval-Augmented Generation) 引擎服務**。此服務同時支援

- **MCP (Model Context Protocol) 模式**： 適用於和 AI 助理（如 Claude Desktop/ChatGPT）的整合。應用範例： 
  * 與 **Claude Desktop** 無縫協作，讓 Claude 在分析您的程式碼或撰寫資安報告時，能自動引用 AIDEFEND 的最新資訊。
  * 支援**其他遵循 Anthropic MCP 標準**的 AI 助理或開發者工具 (包括 OpenAI ChatGPT, Google Gemini)，作為其可引用的本地知識庫。

- **REST API 模式**： 適用於自訂應用程式 (例如，企業內部的資安/AI安全聊天機器人) 與系統整合。應用範例： 
  * 將 AIDEFEND 整合到**企業內部的資安/AI安全聊天機器人**程式，為資安團隊提供即時、精準的防禦指南。
  * 開發一個自動化程式來**放進 CI/CD 流水線**，在部署 AI 模型前，查詢 AIDEFEND 來評估潛在的風險與建議的緩解措施。
  * 將 AIDEFEND 作為一個**RAG（檢索增強生成）的後端**，整合到基於 LangChain、LlamaIndex 或類似框架建立的自定義 LLM 應用程式中。

## 特色功能

- **100% 隱私保護與本地化**: 所有查詢都在本地端處理 - 你輸入的 prompts 只留在你的環境裡，完全支援離線運作
- **多語言支援**: 使用任何語言（中文、日文、韓文等）查詢，都能取得相關的英文內容結果，採用 `intfloat/multilingual-e5-base` (Microsoft, 支援 100+ 語言)
- **成本效益高**: 相較於傳送完整 framework，token 用量減少 25 倍 - 大幅降低 LLM API 成本
- **自動同步**: 自動從 GitHub 下載最新的 AIDEFEND 內容（預設是每小時檢查一次）
- **快速向量搜尋**: 採用 LanceDB 實現快速的語意搜尋（毫秒級回應時間）
- **安全優先**: 全面的輸入驗證、清理與安全Header
- **Docker環境適用**: 可輕鬆透過 Docker 和 docker-compose 部署
- **Prod環境適用**: 包含健康檢查、流量限制、結構化日誌與監控
- **深度防禦**: 多層安全機制（詳見 [SECURITY.md](./SECURITY.md)）

## 為什麼要使用這個 MCP / REST API Service？

AIDEFEND 是開源的，所以理論上呢，你可以自己去 AIDEFEND 的 GitHub Repo 抓取 AIDEFEND 的資料來用，或是直接上 [AIDEFEND 的網站](https://edward-playground.github.io/aidefense-framework/) 並加以查詢使用。但從實際面的角度，有以下的問題:

#### **問題 1: 雲端服務的隱私疑慮**

如果你使用雲端RAG服務的話，大多數 RAG 服務會將你的查詢傳送到雲端伺服器。你的敏感 prompts（安全問題、機敏資訊）有洩漏的可能。

**這個 MCP / REST API Service：**
- ✅ **100% 本地端處理** - 本地查詢
- ✅ **支援離線運作** - 初次同步後可完全離線
- ✅ **零追蹤** - 沒有遙測、沒有外部 API 呼叫

#### **問題 2: LLM 無法處理完整的 AIDEFEND Framework**

AIDEFEND 的防禦手法 (Techniques / Sub-Techniques / Implementation Guidance) 有數千行程式碼。蠻多 LLM 服務有 context window 限制（~8K-128K）。把所有東西貼進 LLM 服務 (ChatGPT/Claude/Gemini/Grok, etc) 有時候會遇到困難。

**這個 MCP / REST API Service：**
- ✅ **智慧搜尋** - 在毫秒內找出 3-5 個最相關的段落
- ✅ **只傳送你需要的** - 不需要手動複製貼上

#### **問題 3: 建立 RAG 系統很複雜**

如果你選擇要自己建立 RAG 功能，你需要：
- 撰寫 JavaScript parser
- 設定 vector database（LanceDB、ChromaDB、Pinecone）
- 配置 embedding models
- 手動處理更新（`git pull` → 重新解析 → 重新 embedding）

**這個 MCP / REST API Service：**
- ✅ **一行指令**: `docker-compose up -d`
- ✅ **每小時自動更新**

#### **問題 4: Token 成本快速累積**

傳送完整的 AIDEFEND framework = 每次查詢 50K+ tokens。付費 LLM API 是按 token 計費的。

**這個 MCP / REST API Service：**
- ✅ **每次查詢 500-2K tokens**（減少 25 倍）
- ✅ **付費 LLM API 成本降低 25 倍**（GPT-4、Claude）

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

   **使用便利腳本：**
   ```bash
   # 在 macOS/Linux 上：
   ./scripts/start.sh

   # 在 Windows 上：
   scripts\start.bat
   ```

   **或直接用 Python 啟動：**
   ```bash
   C:/Python313/python.exe __main__.py
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

      - (在大部分的 Windows 機器上，這個位置可能在: C:\Users\\[您的使用者名稱]\AppData\Roaming\Claude\\)

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

當以 MCP 模式執行時（`C:/Python313/python.exe __main__.py --mcp`），本服務會為 AI 助理（如 Claude Desktop）提供工具。

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

## P0 工具 - 實用範例

AIDEFEND MCP Service 包含 **12 個專門的 P0 工具**，專為 AI 安全從業人員、資安工程師和開發人員設計。這些工具提供比基本知識庫搜尋更強大的目標化功能。

### 工具 1: 取得統計資訊

**用途**: 取得 AIDEFEND 知識庫的完整概覽 - 文件總數、按 tactic/pillar/phase 的涵蓋範圍，以及威脅框架涵蓋範圍。

**何時使用**: 了解知識庫範圍、生成報告、或檢查資料完整性。

#### MCP 模式範例 (Claude Desktop):

```
你: "可以顯示 AIDEFEND 知識庫的統計資訊嗎？"

Claude: [使用 get_statistics 工具]
        AIDEFEND 知識庫包含:
        - 156 份文件總數 (45 個 techniques, 78 個 sub-techniques, 33 個 implementation guidance)
        - 涵蓋 7 種 tactics: Model, Harden, Detect, Isolate, Deceive, Evict, Restore
        - 威脅框架涵蓋範圍: 10 個 OWASP LLM 威脅, 28 個 MITRE ATLAS 技術
        - 34 個 techniques 有開源工具, 18 個有商用工具
        - 42 份文件包含程式碼範例
```

#### REST API 範例:

```bash
curl http://localhost:8000/api/v1/statistics
```

**回應:**
```json
{
  "overview": {
    "total_documents": 156,
    "total_techniques": 45,
    "total_subtechniques": 78,
    "total_guidance": 33
  },
  "by_tactic": {
    "Harden": 18,
    "Detect": 12,
    "Isolate": 8,
    "Model": 7
  },
  "threat_framework_coverage": {
    "owasp_llm_items_covered": 10,
    "mitre_atlas_items_covered": 28,
    "maestro_items_covered": 15
  },
  "tools_availability": {
    "techniques_with_opensource_tools": 34,
    "techniques_with_commercial_tools": 18
  },
  "code_snippets": {
    "documents_with_code_snippets": 42
  }
}
```

---

### 工具 2: 驗證 Technique ID

**用途**: 驗證 technique ID 是否存在且格式正確。如果 ID 不存在，提供模糊匹配建議。

**何時使用**: 查詢特定 techniques 之前、檢查文件中的 ID 是否有效、或尋找相似的 techniques。

#### MCP 模式範例 (Claude Desktop):

```
你: "AID-H-001 是有效的 technique ID 嗎？"

Claude: [使用 validate_technique_id 工具]
        是的，AID-H-001 是有效的！
        - 名稱: Baseline Input Validation
        - 類型: technique
        - Tactic: Harden
```

```
你: "那 AID-H-999 呢？"

Claude: [使用 validate_technique_id 工具]
        AID-H-999 在知識庫中找不到。
        你可能是指：
        - AID-H-001 (Baseline Input Validation) - 85% 匹配
        - AID-H-002 (Prompt Guard) - 78% 匹配
```

#### REST API 範例:

```bash
# 有效的 ID
curl -X POST "http://localhost:8000/api/v1/validate-technique-id?technique_id=AID-H-001"
```

**回應:**
```json
{
  "valid": true,
  "technique": {
    "id": "AID-H-001",
    "name": "Baseline Input Validation",
    "type": "technique",
    "tactic": "Harden"
  }
}
```

```bash
# 無效的 ID（附建議）
curl -X POST "http://localhost:8000/api/v1/validate-technique-id?technique_id=AID-H-999"
```

**回應:**
```json
{
  "valid": false,
  "reason": "NOT_FOUND",
  "suggestions": [
    {
      "id": "AID-H-001",
      "name": "Baseline Input Validation",
      "similarity_score": 0.85
    }
  ]
}
```

---

### 工具 3: 取得 Technique 詳細資訊

**用途**: 取得特定 technique 的完整詳細資訊，包括所有 sub-techniques、帶有程式碼範例的實作策略、工具建議和威脅對應關係。

**何時使用**: 深入研究特定防禦技術、實作防禦控制、或了解某個 technique 可防禦哪些威脅。

#### MCP 模式範例 (Claude Desktop):

```
你: "顯示 technique AID-H-001 的所有詳細資訊"

Claude: [使用 get_technique_detail 工具]
        這是 AID-H-001 (Baseline Input Validation) 的完整分解:

        主要 Technique:
        - Tactic: Harden
        - 防禦: OWASP LLM01, LLM03, MITRE ATLAS AML.T0043

        Sub-Techniques (3 個):
        1. AID-H-001.001: Schema Validation
           - 2 個實作策略，包含 Python/JavaScript 程式碼
        2. AID-H-001.002: Content Filtering
           - 3 個實作策略
        3. AID-H-001.003: Rate Limiting
           - 2 個實作策略

        可用工具:
        - 開源: prompt-toolkit, guardrails-ai, nemo-guardrails
        - 商用: Microsoft Prompt Shield, AWS Bedrock Guardrails
```

#### REST API 範例:

```bash
curl "http://localhost:8000/api/v1/technique/AID-H-001?include_code=true&include_tools=true"
```

**回應** (縮寫):
```json
{
  "technique": {
    "id": "AID-H-001",
    "name": "Baseline Input Validation",
    "type": "technique",
    "tactic": "Harden",
    "description": "實作基線輸入驗證...",
    "defends_against": [
      {
        "framework": "OWASP LLM Top 10",
        "items": ["LLM01", "LLM03"]
      }
    ],
    "tools": {
      "opensource": ["guardrails-ai", "nemo-guardrails"],
      "commercial": ["Microsoft Prompt Shield"]
    }
  },
  "subtechniques": [
    {
      "id": "AID-H-001.001",
      "name": "Schema Validation",
      "guidance": [
        {
          "implementation": "Pydantic-based validation",
          "how_to": "使用 Pydantic models 驗證輸入 schema...",
          "code_blocks": [
            {
              "language": "python",
              "code": "from pydantic import BaseModel..."
            }
          ]
        }
      ]
    }
  ],
  "metadata": {
    "total_subtechniques": 3,
    "total_strategies": 7
  }
}
```

---

### 工具 4: 取得威脅的防禦手法

**用途**: 尋找特定威脅的 AIDEFEND 防禦 techniques。支援 OWASP LLM Top 10、MITRE ATLAS、MAESTRO 的威脅 ID，或自然語言關鍵字。

**何時使用**: 威脅驅動的防禦規劃、回應特定漏洞、或建立防禦路線圖。

#### MCP 模式範例 (Claude Desktop):

```
你: "AIDEFEND 對 OWASP LLM01 有哪些防禦手法？"

Claude: [使用 get_defenses_for_threat 工具]
        針對 OWASP LLM01 (Prompt Injection)，AIDEFEND 建議 8 種防禦 techniques:

        最佳防禦手法:
        1. AID-H-001: Baseline Input Validation (100% 匹配)
        2. AID-H-002: Prompt Guard (100% 匹配)
        3. AID-D-001: Semantic Anomaly Detection (95% 匹配)
        4. AID-I-002: Prompt Isolation (90% 匹配)
```

```
你: "如何防禦模型投毒攻擊？"

Claude: [使用 get_defenses_for_threat 工具進行關鍵字搜尋]
        針對「模型投毒」，這些是相關的防禦手法:

        1. AID-M-001: Training Data Validation (語意匹配: 0.89)
        2. AID-D-003: Model Behavior Monitoring (語意匹配: 0.85)
        3. AID-H-004: Model Integrity Checks (語意匹配: 0.82)
```

#### REST API 範例:

```bash
# 以威脅 ID 搜尋
curl -X POST "http://localhost:8000/api/v1/defenses-for-threat?threat_id=LLM01&top_k=5"
```

**回應:**
```json
{
  "threat_query": {
    "threat_id": "LLM01",
    "normalized_id": "LLM01",
    "threat_keyword": null
  },
  "defense_techniques": [
    {
      "technique": {
        "id": "AID-H-001",
        "name": "Baseline Input Validation",
        "tactic": "Harden"
      },
      "relevance_score": 1.0,
      "match_type": "exact_threat_id",
      "matched_threats": ["LLM01"]
    }
  ],
  "total_results": 5
}
```

```bash
# 以關鍵字搜尋
curl -X POST "http://localhost:8000/api/v1/defenses-for-threat?threat_keyword=prompt%20injection&top_k=10"
```

---

### 工具 5: 取得安全程式碼片段

**用途**: 從 AIDEFEND 實作策略中提取可執行的安全程式碼片段。透過 technique ID 或主題關鍵字搜尋，獲得可直接複製貼上的程式碼範例。

**何時使用**: 實作特定安全控制、尋找程式碼範例、或快速原型開發。

#### MCP 模式範例 (Claude Desktop):

```
你: "顯示輸入驗證的程式碼範例"

Claude: [使用 get_secure_code_snippet 工具]
        我找到 5 個輸入驗證的程式碼片段:

        片段 1 (Python):
        from pydantic import BaseModel, Field

        class UserPrompt(BaseModel):
            text: str = Field(max_length=500)

        def validate_input(prompt: str):
            return UserPrompt(text=prompt)

        片段 2 (JavaScript):
        const Joi = require('joi');
        const schema = Joi.string().max(500).required();
        ...
```

#### REST API 範例:

```bash
# 取得特定 technique 的程式碼
curl -X POST "http://localhost:8000/api/v1/code-snippets?technique_id=AID-H-001.001&max_snippets=5"
```

**回應:**
```json
{
  "query": {
    "technique_id": "AID-H-001.001",
    "topic": null,
    "language_filter": null
  },
  "code_snippets": [
    {
      "technique_id": "AID-H-001.001",
      "technique_name": "Schema Validation",
      "tactic": "Harden",
      "code": "from pydantic import BaseModel, Field\n\nclass UserPrompt(BaseModel):\n    text: str = Field(max_length=500)",
      "language": "python",
      "description": "使用 Pydantic 進行輸入驗證",
      "usage_context": "在傳送給 LLM 前驗證使用者提示"
    }
  ],
  "total_snippets": 5,
  "usage_notes": {
    "security_warning": "在 production 使用前請檢查並測試所有程式碼",
    "adaptation_required": "程式碼片段可能需要適應你的特定環境"
  }
}
```

```bash
# 以主題搜尋並過濾語言
curl -X POST "http://localhost:8000/api/v1/code-snippets?topic=RAG%20security&language=python&max_snippets=3"
```

---

### 工具 6: 分析涵蓋範圍

**用途**: 基於已實作的 techniques 分析防禦涵蓋範圍並識別缺口。提供按 tactic/pillar/phase 的涵蓋百分比、威脅框架涵蓋範圍和優先順序建議。

**何時使用**: 安全程式管理、缺口分析、優先排序安全投資、或向領導層報告。

#### MCP 模式範例 (Claude Desktop):

```
你: "我已實作 AID-H-001、AID-H-002 和 AID-D-001。我的涵蓋範圍如何？"

Claude: [使用 analyze_coverage 工具]
        你的防禦涵蓋範圍分析:

        整體涵蓋: 18% (156 個 techniques 中實作了 3 個)
        涵蓋等級: 最低限度

        按 Tactic 的涵蓋範圍:
        - Harden: 11% (18 個 techniques 中的 2 個)
        - Detect: 8% (12 個 techniques 中的 1 個)
        - Isolate: 0% ⚠️ 重大缺口
        - Model: 0% ⚠️ 重大缺口

        重大缺口:
        1. 沒有 Isolate techniques - 完全缺乏隔離能力
        2. 沒有 Model techniques - 沒有模型強化防禦

        建議的下一步:
        1. 實作 AID-I-001 (Prompt Isolation) - 高優先級
        2. 實作 AID-M-001 (Training Data Validation) - 高優先級
        3. 在 Harden tactic 達到 50%+ 的涵蓋率
```

#### REST API 範例:

```bash
curl -X POST "http://localhost:8000/api/v1/analyze-coverage" \
  -H "Content-Type: application/json" \
  -d '{
    "implemented_techniques": ["AID-H-001", "AID-H-002", "AID-D-001"],
    "system_type": "rag"
  }'
```

**回應:**
```json
{
  "analysis_summary": {
    "total_techniques_available": 156,
    "techniques_implemented": 3,
    "coverage_percentage": 18.0,
    "coverage_level": "Minimal",
    "system_type": "rag"
  },
  "coverage_by_tactic": {
    "Harden": {
      "implemented": 2,
      "total": 18,
      "percentage": 11.1,
      "status": "minimal"
    },
    "Detect": {
      "implemented": 1,
      "total": 12,
      "percentage": 8.3,
      "status": "minimal"
    },
    "Isolate": {
      "implemented": 0,
      "total": 8,
      "percentage": 0.0,
      "status": "not_covered"
    }
  },
  "critical_gaps": [
    {
      "gap_type": "tactic",
      "tactic": "Isolate",
      "severity": "HIGH",
      "reason": "沒有實作 Isolate techniques",
      "risk": "完全缺乏 Isolate 能力"
    }
  ],
  "recommendations": [
    {
      "rank": 1,
      "technique_id": "AID-I-001",
      "name": "Prompt Isolation",
      "tactic": "Isolate",
      "priority": "HIGH",
      "reason": "填補 Isolate tactic 的缺口",
      "impact": "高 - 建立防禦能力"
    }
  ],
  "next_steps": {
    "immediate": [
      "實作 AID-I-001 (Prompt Isolation) - 填補 Isolate tactic 的缺口"
    ],
    "short_term": [
      "在所有 tactics 達到 50%+ 的涵蓋率",
      "涵蓋前 5 個 OWASP LLM 威脅"
    ],
    "long_term": [
      "達到 80%+ 的整體涵蓋率",
      "在所有 pillars 實作縱深防禦"
    ]
  }
}
```

---

### 工具 7: 對應合規框架

**用途**: 將 AIDEFEND techniques 對應到合規框架要求（NIST AI RMF, EU AI Act, ISO 42001, CSA AI Controls, OWASP ASVS），使用啟發式分析。

**100% 本地端** - 使用基於 tactic 對齊的本地啟發式匹配，無外部 API 調用。

**何時使用**: 合規報告、稽核準備、治理文件編制、或展示法規一致性。

#### MCP 模式範例 (Claude Desktop):

```
你: "將 AID-H-001 和 AID-D-001 對應到 NIST AI RMF"

Claude: [使用 map_to_compliance_framework 工具]
        對應到 NIST AI RMF 的合規對應:

        AID-H-001 (Baseline Input Validation):
        - 對應到: GOVERN-1.2, MANAGE-2.1
        - 信心度: 中等
        - 理由: 輸入驗證與風險管理和治理控制相一致

        AID-D-001 (Semantic Anomaly Detection):
        - 對應到: MEASURE-2.1, MANAGE-4.1
        - 信心度: 中等
        - 理由: 偵測技術與測量和事件管理相一致

        ⚠️ 注意: 對應結果應由合規專家審查
```

#### REST API 範例:

```bash
curl -X POST "http://localhost:8000/api/v1/compliance-mapping" \
  -H "Content-Type: application/json" \
  -d '{
    "technique_ids": ["AID-H-001", "AID-D-001"],
    "framework": "nist_ai_rmf"
  }'
```

**回應:**
```json
{
  "framework": {
    "id": "nist_ai_rmf",
    "name": "NIST AI Risk Management Framework"
  },
  "mappings": [
    {
      "technique_id": "AID-H-001",
      "technique_name": "Baseline Input Validation",
      "technique_tactic": "Harden",
      "framework": "nist_ai_rmf",
      "framework_name": "NIST AI Risk Management Framework",
      "framework_controls": ["GOVERN-1.2", "MANAGE-2.1"],
      "mapping_confidence": "medium",
      "mapping_rationale": "基於 tactic 'Harden' 與框架要求的一致性進行對應",
      "additional_considerations": [
        "請與合規團隊審查完整性",
        "視特定使用案例可能需要額外的控制",
        "考慮與其他 techniques 結合以達到完全合規"
      ]
    }
  ],
  "total_mapped": 2,
  "mapping_method": "heuristic",
  "disclaimer": "合規對應使用啟發式分析自動生成，應由合規專家審查。對應可能不涵蓋所有要求，僅應作為指引使用。"
}
```

```bash
# 對應到 EU AI Act
curl -X POST "http://localhost:8000/api/v1/compliance-mapping" \
  -H "Content-Type: application/json" \
  -d '{
    "technique_ids": ["AID-H-001"],
    "framework": "eu_ai_act"
  }'
```

---

### 工具 8: 取得快速參考

**用途**: 為特定安全主題生成快速參考指南。提供按優先順序組織的可行清單（quick wins, must-haves, nice-to-haves）。

**何時使用**: 快速決策、向領導層簡報、新成員入職、或建立安全檢查清單。

#### MCP 模式範例 (Claude Desktop):

```
你: "給我 prompt injection 防禦的快速參考"

Claude: [使用 get_quick_reference 工具]
        快速參考: Prompt Injection 防禦

        🚀 快速成效 (低投入，高影響):
        [ ] AID-H-001: Baseline Input Validation
            投入: 低 | 影響: 高
        [ ] AID-H-002: Prompt Guard
            投入: 低 | 影響: 關鍵

        ⚡ 必要項目 (關鍵防禦):
        [ ] AID-D-001: Semantic Anomaly Detection
            投入: 中 | 影響: 高
        [ ] AID-I-001: Prompt Isolation
            投入: 中 | 影響: 高
        [ ] AID-H-003: Context-Aware Filtering
            投入: 中 | 影響: 高

        ✨ 進階項目 (額外深度):
        [ ] AID-D-002: Behavioral Monitoring
            投入: 高 | 影響: 中
```

#### REST API 範例:

```bash
curl -X POST "http://localhost:8000/api/v1/quick-reference?topic=RAG%20security&format=checklist&max_items=10"
```

**回應:**
```json
{
  "topic": "RAG security",
  "format": "checklist",
  "generated_at": "2025-11-11T12:00:00Z",
  "quick_wins": [
    {
      "priority": 1,
      "technique_id": "AID-H-001",
      "name": "Baseline Input Validation",
      "tactic": "Harden",
      "description": "為 RAG 查詢實作基線輸入驗證...",
      "estimated_effort": "Low",
      "estimated_impact": "High"
    }
  ],
  "must_haves": [
    {
      "priority": 1,
      "technique_id": "AID-H-003",
      "name": "Document Validation",
      "tactic": "Harden",
      "description": "在傳送給 LLM 前驗證檢索到的文件...",
      "estimated_effort": "Medium",
      "estimated_impact": "High"
    }
  ],
  "nice_to_haves": [
    {
      "priority": 1,
      "technique_id": "AID-D-004",
      "name": "Retrieval Monitoring",
      "tactic": "Detect",
      "description": "監控檢索模式以偵測異常...",
      "estimated_effort": "High",
      "estimated_impact": "Medium"
    }
  ],
  "formatted_output": "# 快速成效 (低投入，高影響)\n[ ] AID-H-001: Baseline Input Validation\n    投入: 低 | 影響: 高\n\n# 必要項目 (關鍵防禦)\n[ ] AID-H-003: Document Validation\n    投入: 中 | 影響: 高\n...",
  "total_items": 10,
  "usage_notes": {
    "quick_wins": "低投入，高影響 - 優先實作",
    "must_haves": "關鍵防禦 - 在快速成效後優先實作",
    "nice_to_haves": "額外深度 - 在基礎防禦就緒後實作"
  }
}
```

```bash
# 以 markdown 表格格式取得
curl -X POST "http://localhost:8000/api/v1/quick-reference?topic=model%20hardening&format=table"
```

---

### 工具 9: 取得威脅涵蓋範圍

**用途**: 分析已實作的防禦技術的威脅涵蓋範圍。給定一組 AIDEFEND 技術 ID，計算涵蓋哪些威脅（OWASP LLM Top 10、MITRE ATLAS、MAESTRO）並提供涵蓋率。

**何時使用**: 追蹤已實作防禦涵蓋哪些威脅、識別涵蓋缺口、向利害關係人報告安全態勢、驗證防禦投資。

#### MCP 模式範例 (Claude Desktop):

```
你: "分析技術 AID-D-001、AID-H-002、AID-I-003 的威脅涵蓋範圍"

Claude: [使用 get_threat_coverage 工具]
        威脅涵蓋範圍分析

        分析技術數量: 3
        有效技術: 3
        無效技術: 0

        ## 依框架的威脅涵蓋範圍

        ### OWASP LLM Top 10
        涵蓋率: 30.0% (3/10)
        涵蓋威脅: LLM01, LLM02, LLM03

        ### MITRE ATLAS
        涵蓋率: 4.7% (2/43)
        涵蓋威脅: AML.T0020, AML.T0043

        ## 依技術的涵蓋範圍

        ### AID-D-001: Input Validation
        - OWASP: LLM01
        - ATLAS:

        ### AID-H-002: Prompt Guard
        - OWASP: LLM01, LLM02
        - ATLAS: AML.T0043

        ### AID-I-003: Context Isolation
        - OWASP: LLM03
        - ATLAS: AML.T0020
```

#### REST API 範例:

```bash
curl -X POST "http://localhost:8000/api/v1/threat-coverage" \
  -H "Content-Type: application/json" \
  -d '{
    "implemented_techniques": ["AID-D-001", "AID-H-002", "AID-I-003"]
  }'
```

**回應:**
```json
{
  "input_count": 3,
  "valid_count": 3,
  "invalid_count": 0,
  "invalid_techniques": [],
  "covered": {
    "owasp": ["LLM01", "LLM02", "LLM03"],
    "atlas": ["AML.T0020", "AML.T0043"],
    "maestro": []
  },
  "coverage_rate": {
    "owasp": 0.3,
    "atlas": 0.047,
    "maestro": 0.0
  },
  "by_technique": [
    {
      "technique_id": "AID-D-001",
      "technique_name": "Input Validation",
      "tactic": "Detect",
      "threats_covered": {
        "owasp": ["LLM01"],
        "atlas": [],
        "maestro": []
      }
    }
  ],
  "timestamp": "2025-11-12T10:30:00Z"
}
```

---

### 工具 10: 取得實作計畫

**用途**: 基於啟發式評分（威脅重要性、實作難易度、階段權重、支柱權重）取得下一步要實作的防禦技術排名建議。協助優先安排安全投資。

**何時使用**: 規劃安全路線圖、優先安排技術實作、尋找快速成效、證明安全預算、優化縱深防禦策略。

**注意**: 此工具僅提供啟發式評分。LLM 應使用這些分數透過 RAG 做出最終建議。

#### MCP 模式範例 (Claude Desktop):

```
你: "給我一個實作計畫，排除技術 AID-D-001 和 AID-H-002"

Claude: [使用 get_implementation_plan 工具]
        防禦實作計畫

        已實作技術: 2
        產生建議數量: 10

        ## 優先級分類

        - ⚡ 快速成效 (3 個技術): 高分 + 開源工具可用
        - 🎯 高優先級 (5 個技術): 分數 ≥ 7.0
        - 📋 標準 (2 個技術): 分數 < 7.0

        ## 最佳建議

        🥇 AID-D-014: Prompt Injection Detection
           - 分數: 8.5/10
           - Tactic: Detect
           - Pillar: Detect | Phase: Development
           - 分數分解:
             - 威脅重要性: 3.0/3
             - 實作難易度: 2.0/2
             - 階段權重: 1.5/2
             - 支柱權重: 1.5/2
             - 工具生態系統: 0.5/1
           - 理由: 涵蓋高風險威脅；有開源工具可用；偵測增加縱深防禦
           - ✅ 開源工具可用

        🥈 AID-H-010: Model Input Sanitization
           - 分數: 7.5/10
           - Tactic: Harden
           - Pillar: Prevent | Phase: Design
           - 理由: 涵蓋高風險威脅；早期階段實作 (Design)

        🥉 AID-I-005: Prompt Isolation
           - 分數: 7.0/10
           - Tactic: Isolate
           - Pillar: Prevent | Phase: Development
```

#### REST API 範例:

```bash
curl -X POST "http://localhost:8000/api/v1/implementation-plan" \
  -H "Content-Type: application/json" \
  -d '{
    "implemented_techniques": ["AID-D-001", "AID-H-002"],
    "exclude_tactics": ["Model"],
    "top_k": 10
  }'
```

**回應:**
```json
{
  "input": {
    "implemented_count": 2,
    "exclude_tactics": ["Model"],
    "top_k": 10
  },
  "recommendations": [
    {
      "rank": 1,
      "technique_id": "AID-D-014",
      "technique_name": "Prompt Injection Detection",
      "tactic": "Detect",
      "score": 8.5,
      "score_breakdown": {
        "threat_importance": 3.0,
        "ease_of_implementation": 2.0,
        "phase_weight": 1.5,
        "pillar_weight": 1.5,
        "tool_ecosystem": 0.5
      },
      "reasoning": "Covers high-risk threats; Has open-source tools available; Detection adds defense-in-depth",
      "has_opensource_tools": true,
      "pillar": "Detect",
      "phase": "Development"
    }
  ],
  "categories": {
    "quick_wins": ["AID-D-014", "AID-D-015"],
    "high_priority": ["AID-D-014", "AID-H-010"],
    "standard": ["AID-I-005", "AID-R-001"]
  },
  "timestamp": "2025-11-12T10:30:00Z"
}
```

---

### 工具 11: 威脅分類（雙層本地匹配）

**用途**: 使用快速、本地的雙層匹配系統對文本中的威脅進行分類:
1. **第一層（靜態關鍵字）**: 直接關鍵字匹配（即時）
2. **第二層（RapidFuzz 模糊匹配）**: 容錯匹配（比 difflib 快 10-100 倍）

將常見威脅術語（prompt injection、model poisoning 等）對應到標準框架 ID（OWASP LLM、MITRE ATLAS、MAESTRO）。

**何時使用**: 將事件報告、安全警報、漏洞描述或威脅情報中的威脅關鍵字標準化為標準框架 ID。快速分類安全事件。

**運作方式**:
- 100% 本地端 - 無外部 API 調用，所有處理都在本地端進行
- 第一層：優先嘗試靜態關鍵字匹配（即時精確匹配）
- 第二層：如無靜態匹配，使用 RapidFuzz 進行容錯模糊匹配
- 總是顯示使用哪一層產生的結果（static_keyword、fuzzy_match 或 no_match）

**主要功能**:
- **100% 本地與隱私保護**: 零外部 API 調用，所有處理都在您的機器上進行
- **免費**: 無 API 成本，無 token 消耗
- **快速**: RapidFuzz 毫秒級回應時間（比 difflib 快 10-100 倍）
- **支援離線**: 初次設定後完全離線運作

#### MCP 模式範例 (Claude Desktop):

```
你: "分類以下威脅: '我們偵測到繞過輸入驗證的 prompt injection 攻擊'"

Claude: [使用 classify_threat 工具]
        威脅分類結果

        分類來源: 🔍 靜態關鍵字匹配（第一層）
        輸入文本: 我們偵測到繞過輸入驗證的 prompt injection 攻擊
        匹配關鍵字數量: 2

        ## 匹配關鍵字

        🟢 Prompt Injection (主要, 信心度: 0.9)
        🟡 Insecure Output (別名, 信心度: 0.77)

        ## 標準化威脅 ID

        OWASP LLM Top 10: LLM01, LLM02
        MITRE ATLAS:

        ## 威脅詳情

        - OWASP-LLM01: Prompt Injection
          - 信心度: 0.9
          - 匹配關鍵字: prompt injection
          - 匹配類型: primary

        - OWASP-LLM02: Insecure Output
          - 信心度: 0.77
          - 匹配關鍵字: insecure output
          - 匹配類型: alias

        ## 建議後續步驟

        - get_defenses_for_threat
          - Args: {'threat_id': 'LLM01'}
          - 理由: 尋找 LLM01 的防禦技術

        - get_quick_reference
          - Args: {'topic': 'prompt injection', 'max_items': 10}
          - 理由: 取得 prompt injection 的可行緩解步驟
```

#### REST API 範例:

```bash
curl -X POST "http://localhost:8000/api/v1/classify-threat" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "在我們的 ML pipeline 中偵測到最近的訓練資料投毒攻擊",
    "top_k": 5
  }'
```

**回應:**
```json
{
  "source": "static_keyword",
  "input_text_preview": "在我們的 ML pipeline 中偵測到最近的訓練資料投毒攻擊",
  "keywords_found": [
    {
      "keyword": "training data poisoning",
      "match_type": "primary",
      "confidence": 0.9
    }
  ],
  "normalized_threats": {
    "owasp": ["LLM03"],
    "atlas": ["AML.T0020"],
    "maestro": []
  },
  "threat_details": [
    {
      "threat_id": "OWASP-LLM03",
      "threat_name": "Training Data Poisoning",
      "confidence": 0.9,
      "matched_keyword": "training data poisoning",
      "match_type": "primary"
    },
    {
      "threat_id": "ATLAS-AML.T0020",
      "threat_name": "Training Data Poisoning",
      "confidence": 0.9,
      "matched_keyword": "training data poisoning",
      "match_type": "primary"
    }
  ],
  "recommended_actions": [
    {
      "tool": "get_defenses_for_threat",
      "args": {"threat_id": "LLM03"},
      "reason": "Find defense techniques for LLM03"
    },
    {
      "tool": "get_quick_reference",
      "args": {"topic": "training data poisoning", "max_items": 10},
      "reason": "Get actionable mitigation steps for training data poisoning"
    }
  ],
  "timestamp": "2025-11-12T10:30:00Z"
}
```

---

### 工具 12: 綜合搜尋（多查詢聚合）

**用途**: 使用**多個查詢變化**自動執行並聚合結果，提升召回率和涵蓋範圍。將單一問題重新表述為 3-5 個語義變化，對每個變化執行向量搜尋，然後合併和去重結果。

**何時使用**: 對於廣泛、模糊或跨領域的問題（例如「如何保護 LLM 應用程式」），單次查詢可能遺漏相關內容。綜合搜尋可確保涵蓋範圍，即使問題表述不完美也能找到答案。

**工作原理**:
- 將您的問題自動重新表述為 3-5 個語義變化（本地端）
- 對每個變化平行執行向量搜尋
- 合併所有結果，去除重複項目
- 按相關性分數排序（最相關的優先）

**主要功能**:
- **100% 本地與隱私保護**: 查詢重新表述使用本地文字變化（無外部 API）
- **更好的召回率**: 多查詢策略捕捉更多相關文件
- **容錯**: 即使原始問題表述不佳也能運作

#### MCP 模式範例 (Claude Desktop):

```
你: "我需要全面了解如何保護提示注入攻擊"

Claude: [使用 comprehensive_search 工具]
        綜合搜尋結果

        查詢變化 (3):
        1. "保護提示注入攻擊"
        2. "防禦 LLM 提示操縱漏洞"
        3. "提示注入緩解技術和最佳實踐"

        找到的結果:
        - 總共找到 15 份文件
        - 來自 3 次搜尋的聚合結果
        - 已去除 7 個重複項目

        ## 前 5 項結果

        1. AID-H-001: 輸入驗證與清理（分數: 0.234）
           Pillar: Application Security | Tactic: Harden
           描述: 對所有使用者輸入實施強大的驗證和清理...

        2. AID-D-002: 提示注入偵測（分數: 0.229）
           Pillar: Model Security | Tactic: Detect
           描述: 使用模式匹配和異常偵測來識別惡意提示...

        3. AID-H-003: 輸出過濾與編碼（分數: 0.221）
           Pillar: Application Security | Tactic: Harden
           描述: 過濾和編碼 LLM 輸出以防止注入攻擊...

        [顯示更多結果...]
```

#### REST API 範例:

```bash
curl -X POST "http://localhost:8000/api/v1/comprehensive-search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "如何保護我的 AI 系統免受資料投毒攻擊？",
    "num_variations": 4,
    "top_k_per_query": 5
  }'
```

**回應:**
```json
{
  "original_query": "如何保護我的 AI 系統免受資料投毒攻擊？",
  "query_variations": [
    "如何保護我的 AI 系統免受資料投毒攻擊？",
    "防禦機器學習訓練資料操縱",
    "資料投毒緩解技術",
    "保護 AI 模型訓練管道"
  ],
  "aggregated_results": [
    {
      "source_id": "AID-H-005",
      "name": "訓練資料驗證",
      "text": "對訓練資料實施強大的驗證管道...",
      "score": 0.245,
      "tactic": "Harden",
      "pillar": "Model Security",
      "matched_in_queries": [0, 1, 2]
    },
    {
      "source_id": "AID-D-006",
      "name": "異常資料偵測",
      "text": "監控訓練資料集中的異常模式...",
      "score": 0.238,
      "tactic": "Detect",
      "pillar": "Model Security",
      "matched_in_queries": [1, 3]
    }
  ],
  "total_results": 12,
  "unique_results": 12,
  "duplicates_removed": 8,
  "search_metadata": {
    "num_variations": 4,
    "top_k_per_query": 5,
    "total_searches": 4
  }
}
```

---

### 工具 13: 分析安全態勢

**用途**: 根據已實施的防禦技術，分析 AI 系統的安全態勢。識別涵蓋的威脅、缺口，並提供涵蓋率統計。將已實施的技術對應到 OWASP LLM、MITRE ATLAS 和 MAESTRO 框架。

**何時使用**: 您已部署某些 AIDEFEND 技術，並想了解：
- 我涵蓋了哪些威脅？
- 我遺漏了哪些威脅（缺口）？
- 我的涵蓋率百分比是多少？
- 我應該優先處理什麼？

**工作原理**:
- 輸入已實施技術的 ID 清單（例如 ["AID-H-001", "AID-D-002"]）
- 系統查詢每個技術的 `defends_against` 元數據
- 將涵蓋的威脅對應到框架（OWASP/ATLAS/MAESTRO）
- 計算涵蓋率百分比並識別缺口
- 提供可執行的建議以填補缺口

**主要功能**:
- **100% 本地與隱私保護**: 所有分析都使用本地元數據
- **快速涵蓋率分析**: 數秒內了解您的態勢
- **可執行的缺口識別**: 準確知道遺漏的內容

#### MCP 模式範例 (Claude Desktop):

```
你: "分析我的安全態勢。我已實施 AID-H-001、AID-H-002 和 AID-D-001"

Claude: [使用 analyze_security_posture 工具]
        安全態勢分析

        已實施技術: 3
        - AID-H-001: 輸入驗證與清理
        - AID-H-002: 輸出過濾
        - AID-D-001: 異常偵測

        ## 威脅涵蓋率

        OWASP LLM Top 10: 4/10 涵蓋 (40%)
        涵蓋: LLM01, LLM02, LLM06, LLM08
        缺口: LLM03, LLM04, LLM05, LLM07, LLM09, LLM10

        MITRE ATLAS: 6/28 涵蓋 (21%)
        涵蓋: AML.T0015, AML.T0043, AML.T0051...
        缺口: AML.T0020, AML.T0025, AML.T0034...

        MAESTRO: 2/15 涵蓋 (13%)
        涵蓋: MAE-001, MAE-003
        缺口: MAE-002, MAE-004, MAE-005...

        ## 建議

        優先處理這些缺口:
        1. LLM03: 訓練資料投毒 (高風險)
           建議: 實施 AID-H-005 (訓練資料驗證)

        2. LLM05: 供應鏈漏洞 (高風險)
           建議: 實施 AID-H-010 (依賴掃描)

        3. AML.T0020: 後門攻擊
           建議: 實施 AID-D-008 (模型行為監控)
```

#### REST API 範例:

```bash
curl -X POST "http://localhost:8000/api/v1/security-posture" \
  -H "Content-Type: application/json" \
  -d '{
    "implemented_techniques": ["AID-H-001", "AID-H-002", "AID-D-001"],
    "include_recommendations": true
  }'
```

**回應:**
```json
{
  "implemented_techniques": ["AID-H-001", "AID-H-002", "AID-D-001"],
  "coverage_summary": {
    "owasp": {
      "covered": ["LLM01", "LLM02", "LLM06", "LLM08"],
      "gaps": ["LLM03", "LLM04", "LLM05", "LLM07", "LLM09", "LLM10"],
      "coverage_percentage": 40.0,
      "total_threats": 10
    },
    "atlas": {
      "covered": ["AML.T0015", "AML.T0043", "AML.T0051"],
      "gaps": ["AML.T0020", "AML.T0025"],
      "coverage_percentage": 21.4,
      "total_threats": 28
    },
    "maestro": {
      "covered": ["MAE-001", "MAE-003"],
      "gaps": ["MAE-002", "MAE-004"],
      "coverage_percentage": 13.3,
      "total_threats": 15
    }
  },
  "recommendations": [
    {
      "threat_id": "LLM03",
      "threat_name": "Training Data Poisoning",
      "severity": "HIGH",
      "recommended_techniques": [
        {
          "id": "AID-H-005",
          "name": "訓練資料驗證",
          "rationale": "直接防禦訓練資料投毒攻擊"
        }
      ]
    }
  ],
  "overall_score": 24.9
}
```

---

### 工具 14: 比較技術

**用途**: 使用**啟發式評分**並排比較多個 AIDEFEND 技術的有效性、複雜度和成本。幫助您在競爭防禦選項之間做出明智的決策。

**何時使用**: 您有多個技術選項來解決威脅，需要了解：
- 哪個最有效？
- 哪個最容易實施？
- 哪個成本最低？
- 最佳效益/複雜度比率是什麼？

**工作原理**:
- 輸入 2-10 個技術 ID 進行比較（例如 ["AID-H-001", "AID-D-002"]）
- 系統使用啟發式演算法計算每個技術的分數：
  - **有效性分數 (0-100)**: 基於威脅涵蓋範圍、實施支援、程式碼片段
  - **複雜度分數 (0-100)**: 基於子技術、pillar、phase、策略數量
  - **成本分數 (0-100)**: 基於商用/開源工具、基礎設施需求
- 提供優先順序建議（快速獲勝、策略投資）

**主要功能**:
- **100% 本地與隱私保護**: 所有評分都使用本地元數據分析
- **無 ML 推論成本**: 啟發式評分（無外部 API）
- **可執行的建議**: 清晰的優先順序指引

#### MCP 模式範例 (Claude Desktop):

```
你: "比較 AID-H-001、AID-D-002 和 AID-I-003。哪個應該優先？"

Claude: [使用 compare_techniques 工具]
        技術比較矩陣

        比較 3 個技術:

        ## 比較結果

        | 技術 | 有效性 | 複雜度 | 成本 | 威脅涵蓋 |
        |------|--------|--------|------|----------|
        | AID-H-001 | 85 | 40 | 30 | OWASP: 3, ATLAS: 2 |
        | AID-D-002 | 78 | 55 | 45 | OWASP: 2, ATLAS: 4 |
        | AID-I-003 | 72 | 65 | 60 | OWASP: 2, ATLAS: 3 |

        ## 建議

        🎯 快速獲勝（高效益、低複雜度、低成本）:
        - AID-H-001: 輸入驗證與清理
          有效性: 85, 複雜度: 40, 成本: 30

        📈 實施優先順序（按效益/複雜度比率）:
        1. AID-H-001 (比率: 2.13)
        2. AID-D-002 (比率: 1.42)
        3. AID-I-003 (比率: 1.11)

        💡 策略投資（高效益，但需要大量資源）:
        - 無（所有技術的複雜度/成本都可管理）
```

#### REST API 範例:

```bash
curl -X POST "http://localhost:8000/api/v1/compare-techniques" \
  -H "Content-Type: application/json" \
  -d '{
    "technique_ids": ["AID-H-001", "AID-D-002", "AID-I-003"],
    "include_recommendations": true
  }'
```

**回應:**
```json
{
  "input_techniques": ["AID-H-001", "AID-D-002", "AID-I-003"],
  "comparison_matrix": [
    {
      "source_id": "AID-H-001",
      "name": "輸入驗證與清理",
      "tactic": "Harden",
      "pillar": "Application Security",
      "effectiveness_score": 85,
      "complexity_score": 40,
      "cost_score": 30,
      "threat_coverage": {
        "owasp": 3,
        "atlas": 2,
        "maestro": 1
      },
      "has_implementation_guidance": true,
      "has_code_snippets": true
    },
    {
      "source_id": "AID-D-002",
      "name": "異常偵測",
      "tactic": "Detect",
      "pillar": "Model Security",
      "effectiveness_score": 78,
      "complexity_score": 55,
      "cost_score": 45,
      "threat_coverage": {
        "owasp": 2,
        "atlas": 4,
        "maestro": 0
      },
      "has_implementation_guidance": true,
      "has_code_snippets": false
    }
  ],
  "summary": {
    "techniques_compared": 3,
    "average_effectiveness": 78.3,
    "average_complexity": 53.3,
    "average_cost": 45.0,
    "tactics_covered": ["Harden", "Detect", "Isolate"],
    "pillars_covered": ["Application Security", "Model Security", "Infrastructure Security"]
  },
  "recommendations": [
    {
      "category": "快速獲勝",
      "description": "高效益、低複雜度、低成本",
      "techniques": [
        {"id": "AID-H-001", "name": "輸入驗證與清理"}
      ]
    },
    {
      "category": "實施優先順序",
      "description": "按效益/複雜度比率排序",
      "techniques": [
        {"id": "AID-H-001", "name": "輸入驗證與清理"},
        {"id": "AID-D-002", "name": "異常偵測"},
        {"id": "AID-I-003", "name": "網路隔離"}
      ]
    }
  ]
}
```

---

### 工具 15: 生成事件應變劇本

**用途**: 根據威脅分類生成結構化的 AI 安全事件應變劇本。提供基於時間軸的行動計畫，遵循 NIST 事件應變階段，包含可執行的步驟和預估時間。

**何時使用**: 發生安全事件時（例如提示注入偵測、資料投毒懷疑、模型萃取嘗試），您需要：
- 結構化的應變計畫
- 基於時間軸的行動項目
- 威脅特定的緩解步驟
- 復原和修復指引

**工作原理**:
- 輸入事件描述（例如「在生產環境 LLM 中偵測到可疑的提示注入嘗試」）
- 系統使用 `classify_threat` 工具識別威脅
- 使用 `get_defenses_for_threat` 工具取得防禦技術
- 生成 4 階段時間軸（NIST 事件應變週期）：
  1. **立即行動** (0-15 分鐘)
  2. **調查** (15 分鐘 - 2 小時)
  3. **遏制** (2-8 小時)
  4. **復原與修復** (8+ 小時)
- 每個行動項目包含優先級、描述、預估時間

**主要功能**:
- **100% 本地與隱私保護**: 所有劇本生成都使用本地邏輯
- **威脅感知**: 根據威脅類型自訂行動項目
- **可執行的時間軸**: 清晰的階段和時間預估

#### MCP 模式範例 (Claude Desktop):

```
你: "生成事件應變劇本：在生產環境 LLM API 中偵測到提示注入攻擊"

Claude: [使用 generate_incident_playbook 工具]
        事件應變劇本

        ## 事件摘要

        描述: 在生產環境 LLM API 中偵測到提示注入攻擊
        總行動項目: 18
        預估總時間: 1-3 天（視嚴重程度和複雜度而定）

        主要威脅: OWASP-LLM01: Prompt Injection (信心度: 90%)

        ## 時間軸

        ### 階段 1: 立即行動 (0-15 分鐘)
        目標: 初步回應、證據保存和遏制

        ✅ 1. 啟動事件應變團隊（優先級: CRITICAL）
           - 通知指定的 IR 團隊成員並建立溝通管道
           - 預估時間: 2-5 分鐘

        ✅ 2. 評估初始嚴重程度（優先級: CRITICAL）
           - 根據初步觀察判定嚴重程度等級（低/中/高/嚴重）
           - 預估時間: 5-10 分鐘

        ✅ 3. 保存證據（優先級: HIGH）
           - 在任何修改之前擷取日誌、截圖、系統狀態。記錄時間軸。
           - 預估時間: 5-10 分鐘

        ✅ 4. 隔離受影響的 LLM 端點（優先級: CRITICAL）
           - 暫時停用或限速受影響的 LLM API 端點以防止利用
           - 預估時間: 5 分鐘

        ### 階段 2: 調查 (15 分鐘 - 2 小時)
        目標: 威脅分析、範圍確定和根本原因識別

        🔍 5. 執行威脅分類（優先級: HIGH）
           - 將事件對應到 OWASP LLM Top 10、MITRE ATLAS 或 MAESTRO 框架
           - 預估時間: 10-15 分鐘
           - 工具: classify_threat 工具

        🔍 6. 收集入侵指標 (IOCs)（優先級: HIGH）
           - 收集 IP 位址、使用者 ID、時間戳記、請求模式、模型輸出
           - 預估時間: 20-30 分鐘

        🔍 7. 範圍分析（優先級: HIGH）
           - 確定哪些系統、模型和使用者受到影響。評估資料曝光。
           - 預估時間: 30-45 分鐘

        ### 階段 3: 遏制 (2-8 小時)
        目標: 隔離威脅、部署防禦並防止進一步損害

        🛡️ 8. 隔離受影響系統（優先級: CRITICAL）
           - 視需要進行網路分段、API 端點停用、使用者帳戶暫停
           - 預估時間: 30-60 分鐘

        🛡️ 9. 阻止攻擊向量（優先級: HIGH）
           - 實施輸入驗證、輸出過濾或存取控制以防止持續利用
           - 預估時間: 1-2 小時

        🛡️ 10. 實施提示驗證（優先級: HIGH）
           - 部署輸入清理和提示注入偵測機制
           - 預估時間: 2-4 小時

        ### 階段 4: 復原與修復 (8+ 小時)
        目標: 恢復作業、實施長期修復並記錄經驗教訓

        🔧 11. 實施安全控制（優先級: HIGH）
           - 部署調查期間識別的建議 AIDEFEND 防禦技術
           - 預估時間: 4-8 小時

        🔧 12. 安全恢復服務（優先級: MEDIUM）
           - 在增強監控和控制下逐步恢復受影響的服務
           - 預估時間: 2-4 小時

        🔧 13. 進行事後檢討（優先級: MEDIUM）
           - 記錄經驗教訓、更新手冊、識別流程改進
           - 預估時間: 2-3 小時

        ## 防禦技術

        建議部署 5 個 AIDEFEND 技術:
        - AID-H-001: 輸入驗證與清理
        - AID-D-002: 提示注入偵測
        - AID-H-003: 輸出過濾與編碼
        [...]
```

#### REST API 範例:

```bash
curl -X POST "http://localhost:8000/api/v1/incident-playbook" \
  -H "Content-Type: application/json" \
  -d '{
    "incident_description": "模型輸出在生產環境中洩露訓練資料",
    "include_defense_techniques": true
  }'
```

**回應:**
```json
{
  "incident_summary": {
    "description": "模型輸出在生產環境中洩露訓練資料",
    "total_action_items": 16,
    "phases": 4,
    "estimated_total_time": "1-3 天（視嚴重程度和複雜度而定）",
    "primary_threat": {
      "threat_id": "LLM06",
      "framework": "OWASP LLM Top 10",
      "description": "Sensitive Information Disclosure",
      "confidence": 85
    }
  },
  "threat_classification": {
    "source": "static_keyword",
    "matched_threats": [
      {
        "threat_id": "OWASP-LLM06",
        "keyword": "training data disclosure",
        "confidence": 85
      }
    ]
  },
  "timeline": {
    "immediate": {
      "phase": "立即行動",
      "timeframe": "0-15 分鐘",
      "objective": "初步回應、證據保存和遏制",
      "actions": [
        {
          "action": "啟動事件應變團隊",
          "priority": "CRITICAL",
          "description": "通知指定的 IR 團隊成員並建立溝通管道",
          "estimated_time": "2-5 分鐘"
        },
        {
          "action": "評估初始嚴重程度",
          "priority": "CRITICAL",
          "description": "根據初步觀察判定嚴重程度等級",
          "estimated_time": "5-10 分鐘"
        }
      ]
    },
    "investigation": {
      "phase": "調查",
      "timeframe": "15 分鐘 - 2 小時",
      "objective": "威脅分析、範圍確定和根本原因識別",
      "actions": [...]
    },
    "containment": {
      "phase": "遏制",
      "timeframe": "2-8 小時",
      "objective": "隔離威脅、部署防禦並防止進一步損害",
      "actions": [...]
    },
    "recovery": {
      "phase": "復原與修復",
      "timeframe": "8+ 小時",
      "objective": "恢復作業、實施長期修復並記錄經驗教訓",
      "actions": [...]
    }
  },
  "defense_techniques": {
    "threat_id": "LLM06",
    "techniques": [
      {
        "source_id": "AID-H-007",
        "name": "輸出過濾與清理",
        "score": 0.234,
        "defends_against": ["LLM06"]
      }
    ]
  },
  "generated_at": "2025-11-18T10:30:00Z"
}
```

---

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
| `MAX_QUERY_LENGTH` | `1500` | 查詢文字的最大長度（對齊嵌入模型限制）|
| `API_WORKERS` | `1` | ⚠️ **必須為 1** - 不支援多 worker 模式 |
| `ENABLE_FUZZY_MATCHING` | `true` | 啟用第二層模糊匹配以容錯（100% 本地端）|
| `FUZZY_MATCH_CUTOFF` | `0.70` | 模糊匹配的最小相似度分數（0.0-1.0）|

### 重要：單一 Worker 限制

**⚠️ 本服務需要 `API_WORKERS=1`**

同步架構使用檔案鎖定和記憶體內狀態管理，需要單一 worker process。使用 `API_WORKERS > 1` 會導致：

- 同步衝突和競態條件
- 某些 worker 在同步後提供過時資料
- 查詢結果不一致

**在 production 部署時**，如果需要水平擴展：
- 在負載平衡器後部署多個獨立實例
- 使用獨立的同步服務/cron job 更新共享資料庫
- 每個 API 實例執行時設定 `API_WORKERS=1`

### 100% 本地處理 - 隱私保證

**本服務完全本地化且私密:**

✅ **零外部 API 調用**
- 所有威脅分類都使用雙層匹配（靜態 + RapidFuzz）在本地端進行
- 所有知識庫查詢都在您的機器上處理
- 嵌入生成使用本地 ONNX 模型（FastEmbed）
- 資料絕不會離開您的基礎設施

✅ **免費 - 無 API 成本**
- 任何功能都不需要 API 金鑰
- 無 token 消耗
- 零持續成本

✅ **100% 離線運作**
- 從 GitHub 初次同步後，完全離線運作
- 查詢時不需要網路連線
- 適合空氣隔離/受限環境

✅ **隱私優先**
- 您的查詢、資料和威脅情報都保留在您的機器上
- 無遙測、無追蹤、無外部日誌記錄
- 符合受監管產業（醫療、金融、政府）的合規要求

**架構流程:**
```
您的查詢 → 本地匹配引擎（第一層：靜態、第二層：RapidFuzz）
           ↓
本地向量資料庫（LanceDB）→ 本地嵌入模型（FastEmbed/ONNX）
           ↓
結果（100% 在您的機器上處理）✅
```

**未來增強功能（選用）:**
- 第三層本地嵌入語義匹配（使用現有的 FastEmbed）
- 仍然 100% 本地端、零成本、無外部 API 調用
- 請參閱 GitHub issues 了解實作時程

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

### 健康檢查端點

`/health` endpoint 提供全面的服務健康狀態：

```bash
curl http://localhost:8000/health
```

**回應：**
```json
{
  "status": "healthy",  // 或 "degraded"、"unhealthy"
  "checks": {
    "database": true,
    "embedding_model": true,
    "sync_service": true
  },
  "timestamp": "2025-11-11T00:00:00Z"
}
```

**健康狀態等級：**
- `healthy` - 所有系統正常運作，資料新鮮
- `degraded` - 系統可運作但資料過時（上次同步 > 2x 同步間隔）
- `unhealthy` - 關鍵元件故障（資料庫、embedding model）

**過時資料偵測：**
健康檢查會自動偵測同步是否長時間失敗。如果資料年齡超過 `2 × SYNC_INTERVAL_SECONDS`，狀態會變為 `degraded` 以警告監控系統。

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

### 自動化安全掃描

本 repository 包含自動化安全掃描，透過 GitHub Actions 執行：

**🔒 安全工作流程 (`.github/workflows/security.yml`)**
- **Bandit**: Python 程式碼靜態安全分析
- **Safety**: 相依套件漏洞掃描
- **CodeQL**: 進階語義程式碼分析

**自動執行時機：**
- 每次 push 到 `main` 或 `develop` 分支
- 所有 pull request
- 每週排程（週一 00:00 UTC）
- 可透過 GitHub Actions UI 手動觸發

**📦 Dependabot (`.github/dependabot.yml`)**
- 自動化相依套件更新
- 每週掃描 Python 套件和 GitHub Actions
- 自動發送 PR 修補安全漏洞
- 開發用相依套件集中更新

**查看安全報告：** 檢查 GitHub repository 的「Security」標籤。

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
├── scripts/             # 便利腳本
│   ├── start.sh         # 快速啟動腳本（Unix）
│   └── start.bat        # 快速啟動腳本（Windows）
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
   C:/Python313/python.exe __main__.py --mcp
   ```
   - 你應該會在 stderr 看到「Starting AIDEFEND MCP Server (stdio mode)...」
   - 如果當機，請檢查錯誤訊息

#### MCP 工具速度慢或逾時

- 首次查詢會觸發初始同步（1-3 分鐘）
- 檢查同步是否完成：`C:/Python313/python.exe __main__.py` 然後造訪 http://localhost:8000/api/v1/status
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


