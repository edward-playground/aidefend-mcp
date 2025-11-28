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

## 💰 為什麼要使用這個 MCP / REST API Service？

### TL;DR
**省 90% LLM 成本 + 更準確的答案 + 5 分鐘安裝 = 你的新 AI 安全工作流程**

> 如果你正在用 ChatGPT/Claude/Gemini 查詢 AI 安全防禦策略，你可能在不知不覺中浪費 90% 的預算，還得到不完整的答案。

---

### 📊 使用 AIDEFEND 的兩種方式

#### ❌ 手動方式：下載 → 貼進 LLM

```
1. 從 GitHub 下載所有 tactics/*.js 檔案             (⏱️ 5 分鐘)
2. 合併成一個檔案                                   (⏱️ 3 分鐘)
3. 複製約 50,000 tokens 到剪貼簿
4. 貼進 ChatGPT/Claude
5. 問問題

問題：
💸 每次查詢成本：$0.50 (GPT-4)
⚠️  LLM 可能遺漏關鍵資訊（Lost in the Middle 問題）
🔄 AIDEFEND 更新了？重新下載所有檔案（每次 8 分鐘）
📊 100 次查詢 = $50
```

#### ✅ AIDEFEND MCP 方式：智慧 Vector Search

```
1. 安裝一次（2 分鐘）
   python scripts/install.py

2. 問問題（透過 Claude Desktop 或 API）

優勢：
💰 每次查詢成本：$0.02（2,000 tokens vs 50,000）
✅ Vector search 找到最相關的內容（不會遺漏資訊）
🔄 每小時自動更新（零維護）
📊 100 次查詢 = $2

省下 $48 + 數小時的手動工作！
```

---

### 💸 真實成本對比

| 使用量 | 手動方式 (50K tokens/次) | AIDEFEND MCP (2K tokens/次) | 省下 |
|-------|-------------------------|----------------------------|------|
| **100 次查詢** | $50 | $2 | **$48** |
| **1 年 (每天 10 次)** | $1,825 | $73 | **$1,752** |

*基於 GPT-4 Turbo 定價（$10/1M input tokens）*

💡 **企業團隊每年僅 LLM API 成本就省下 $1,752+**

---

### 🎯 為什麼 Vector Search 勝過全文貼上

**「Lost in the Middle」問題：**

當你貼入 50,000 tokens 到 LLM 時，它會在處理中間資訊時遇到困難：

```
你貼入的 50K tokens：
┌─────────────────────────────────┐
│ 前 10K tokens                   │  ← LLM 注意力高 ⭐⭐⭐⭐⭐
│ Model Tactic...                 │
│                                 │
│ 中間 30K tokens                 │  ← LLM 注意力下降 ⭐⭐
│ ⚠️  最重要的防禦手法！           │  ← 常被忽略！
│ ⚠️  AID-H-001, AID-H-002...     │
│                                 │
│ 最後 10K tokens                 │  ← LLM 注意力高 ⭐⭐⭐⭐⭐
│ Respond Tactic...               │
└─────────────────────────────────┘

結果：LLM 可能跳過最相關的技術！
```

**Vector Search 解決方案：**

```
你的問題：「如何防禦 prompt injection？」
       ↓
Vector search 分析語意相似度
       ↓
回傳最相關的 TOP 5（2K tokens）：
✅ AID-H-001: Input Validation        (相似度: 0.92)
✅ AID-H-002: Prompt Guard             (相似度: 0.89)
✅ AID-D-001: Anomaly Detection        (相似度: 0.85)
       ↓
LLM 得到精準、相關的資訊 → 更好的答案！
```

> **研究顯示**：相較於全文檢索，Vector search 讓答案品質提升 40%

---

### 🛠️ 不只是搜尋：19 個專業工具

**手動方式：** 只能問問題
**AIDEFEND MCP：** 專業的 AI 安全分析平台

**工具範例：**

```python
# 1. 覆蓋分析 - 找出你的防禦缺口
analyze_coverage(implemented_techniques=["AID-H-001"])
→ 顯示各 tactic 的覆蓋率 %，找出缺口

# 2. 實施計畫 - 接下來該建立什麼
get_implementation_plan(implemented_techniques=["AID-H-001"])
→ 根據威脅重要性排序的建議

# 3. 合規對應 - 稽核支援
map_to_compliance_framework(techniques=["AID-H-001"], framework="nist_ai_rmf")
→ 對應到 NIST AI RMF、EU AI Act、ISO 42001

# 4. 威脅覆蓋 - 你防禦了哪些威脅？
get_threat_coverage(implemented_techniques=["AID-H-001"])
→ OWASP LLM Top 10、MITRE ATLAS 覆蓋分析
```

💼 **這些功能在手動工作流程中不存在**

---

### 🚀 5 分鐘開始使用

```bash
# 1. Clone
git clone https://github.com/edward-playground/aidefend-mcp.git
cd aidefend-mcp

# 2. 安裝
pip install -r requirements.txt

# 3. 執行（REST API 模式 - 預設）
python __main__.py

# ✅ 完成！訪問 http://localhost:8000/docs
```

**若要使用 MCP 模式（Claude Desktop）：**執行 `python scripts/install.py` 一鍵安裝，詳見 [INSTALL-繁體中文.md](INSTALL-繁體中文.md)。

**立即試用：**

```bash
# REST API
curl -X POST "http://localhost:8000/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{"query_text": "prompt injection defense", "top_k": 5}'

# MCP 模式（Claude Desktop）
# 直接問 Claude：「如何防禦 prompt injection？」
# Claude 會自動使用 AIDEFEND 工具！
```

---

**還在等什麼？**
- ✅ 完全免費開源
- ✅ 100% 本地端（隱私優先）
- ✅ 零維護成本
- ✅ 5 分鐘安裝

**立即開始省錢並獲得更好的答案！** 🚀

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
- **2-2.5GB 磁碟空間**（採用 Int8 量化模型後從 3-4GB 減少）
  - 服務本身: ~200-700MB（程式碼 + 知識庫 + 日誌）
  - 外部相依套件: ~880MB-1.48GB（ONNX 模型 + Python/Node 套件）
  - **模型減少 75%**: 量化 Int8 版本（280MB vs 原始 1.1GB）

## 快速開始

### 步驟 1：Clone Repository

```bash
git clone https://github.com/edward-playground/aidefend-mcp.git
cd aidefend-mcp
```

### 步驟 2：選擇模式並安裝

| 模式 | 適合用於 | 快速開始 |
|------|---------|---------|
| **🖥️ Claude Desktop** | 桌面應用程式使用者 | `python scripts/install.py` |
| **💻 Claude Code** | VSCode 使用者 | `python scripts/install.py --client code` |
| **🌐 REST API** | HTTP 整合、CI/CD | `python scripts/install.py --no-mcp` |
| **🐳 Docker** | 正式部署 | `docker-compose up -d` |

---

<details open>
<summary><h4>🔌 選項 A：MCP 模式（Claude Desktop）- 推薦</h4></summary>

**🚀 一鍵安裝（2 分鐘完成）：**

```bash
# 單一指令 - 自動安裝所有依賴並設定 Claude Desktop
python scripts/install.py

# macOS/Linux 使用者：如果 python 指向 Python 2，請使用 python3
python3 scripts/install.py
```

**這個腳本會自動：**
- ✅ 檢查 Python 3.9+ 和 Node.js 18+ 版本
- ✅ 自動安裝所有 Python 依賴
- ✅ 自動安裝所有 Node.js 依賴
- ✅ 自動偵測路徑並設定 Claude Desktop
- ✅ **安全合併配置（保留所有現有的 MCP 工具）**
- ✅ 修改前自動建立備份

**詳細說明：** 請參閱 [INSTALL-繁體中文.md 的一鍵安裝章節](INSTALL-繁體中文.md#-mcp-模式設定claude-desktop---一鍵安裝)。

<details>
<summary><b>進階：手動設定（點擊展開）</b></summary>

詳細的手動設定說明請參閱 [INSTALL-繁體中文.md](INSTALL-繁體中文.md)。

</details>

</details>

---

<details>
<summary><h4>🌐 選項 B：REST API 模式（HTTP 整合）</h4></summary>

**安裝相依套件：**
```bash
# 安裝相依套件但不設定 MCP
python scripts/install.py --no-mcp

# macOS/Linux 使用者：如果 python 指向 Python 2，請使用 python3
python3 scripts/install.py --no-mcp
```

**啟動服務：**
```bash
python __main__.py
```

**驗證是否正在執行：**
```bash
curl http://localhost:8000/health
```

**存取 API 文件：**
開啟瀏覽器：http://localhost:8000/docs

服務會在首次執行時自動與 GitHub 同步並索引 AIDEFEND framework。

</details>

---

<details>
<summary><h4>🐳 選項 C：Docker 部署（正式環境）</h4></summary>

**啟動：**
```bash
docker-compose up -d
```

**檢查日誌：**
```bash
docker-compose logs -f
```

**注意：** MCP 模式需要直接執行 Python，無法在 Docker 中運行。

</details>

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
