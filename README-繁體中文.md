[English README](README.md) | [繁體中文 README](README-繁體中文.md)

---

# AIDEFEND MCP / REST API Service

[![CI](https://github.com/edward-playground/aidefend-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/edward-playground/aidefend-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%20|%203.13-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.121.1-009688.svg)](https://fastapi.tiangolo.com)

這個 repo 是 [AIDEFEND framework](https://github.com/edward-playground/aidefense-framework) 的本地檢索服務層。

它會安全地解析 framework 的 JavaScript tactics 檔、建立本地 LanceDB 知識庫，並透過以下兩種方式提供查詢能力：

- REST API，給應用程式、腳本與系統整合使用
- MCP server，給 Claude Desktop 這類 AI 助理使用

這個 repo **不是** framework 本體，而是建在 framework 之上的服務。

## 你會得到什麼

- 可在本地執行的 AIDEFEND 語意搜尋
- 同一套知識庫，同時提供 REST API 與 MCP
- 預設直接從 GitHub 同步上游 framework
- 若你同時開發兩個 repo，可選擇使用本機 framework 路徑覆寫
- 使用 `Xenova/multilingual-e5-base` 做多語言 embedding 搜尋
- GitHub Actions 自動跑 `pytest` 與 `bandit`

## 它怎麼運作

1. 從 GitHub 同步 AIDEFEND tactic 檔。
2. 用 Node.js AST parser 解析 JavaScript。這個服務不會執行上游 framework code。
3. 把 tactics 展開成 techniques、sub-techniques 與 strategies。
4. 產生 embeddings 並寫入 LanceDB。
5. 透過 REST 或 MCP 對外提供查詢。

## 持續相容上游更新

目前 release 的精確驗證快照是 AIDEFEND **1.20260724**、authoring schema
**1.7**、public schema **2.3** 與 index schema **3.2**，並涵蓋 framework
的三種工具分類：開源、source-available/open-weight 與商業工具。快照中的
ID、標題、筆數與順序只是這個 release 的驗證範例，不是永久的 runtime 限制。

在已支援的 framework 契約內，每次同步都會從指定來源動態重建 MCP 與 REST
共用的資料。新增或移除內容、ID 重新編號、標題或 guidance 修改、筆數或順序
改變，以及相容的新增欄位，都不需要針對個別客戶設定。威脅框架標籤也由來源資料決定；
新增或更名的標籤會繼續進入涵蓋率與分析結果，不會綁死在這份快照裡現有的名稱。
即使極長的 scope boundary 或工具內容超過 embedding model 可搜尋的 token window，
完整值仍會保留在 MCP／REST 的結構化 metadata；此情況會留下警告，不會拒絕其他部分都有效的更新。

每次檢查更新時，服務會嘗試讀取與 tactic 檔相同的本機 framework root，或同一個不可變
GitHub commit 根目錄中的 `data-schema.md`。檔案存在時，會記錄 authoring、public schema 版本
與 SHA-256 digest。如果這份選用的 metadata 不存在，或無法辨識其中版本，可記為 `unknown`，
但不會只因這點中斷相容內容的同步；候選 index 仍必須通過完整驗證。

自動同步預設啟用，服務啟動時會立即檢查一次，之後每隔 `SYNC_INTERVAL_SECONDS` 秒檢查；
預設為 3600 秒，可設為 60 到 86400 秒，連續失敗時會退避。這是 runtime 更新節奏；另外，
rolling daily upstream canary 會每天驗證最新公開 framework，並保留精確 release 快照驗證。

本服務不宣稱能自動相容任意的破壞性 schema 變更。所有候選 index 都必須先
通過驗證才會啟用；如果上游來源無效或確實不相容，既有安裝會讓 MCP 與 REST
繼續使用 last-known-good index，並回報同步錯誤。版本 metadata 採原子替換寫入；若新資料庫啟用後，
版本 metadata 的最後寫入失敗，會先將未完成交付的資料庫下線，並在存在時復原 last-known-good 資料庫。
首次安裝若尚未建立任何已驗證 index，則會明確失敗，而不會發布不完整或誤解的資料；
新的破壞性契約必須透過後續版本明確支援。
例如第四種具語意的工具分類或既有欄位 shape 改變，會視為破壞性契約並拒絕，
而不是靜默忽略資料。

## 需求

- Python 3.10 到 3.13
- Node.js 18+
- Git
- 約 2 到 3 GB 可用磁碟空間，包含依賴、embedding model 與本地資料庫

安裝與執行都不需要 `npm`。Acorn parser 已隨 repository 放在 `vendor/`，
JavaScript 執行環境只需要 Node.js 18+。

一般使用者**不需要**設定任何個人本機路徑。預設安裝流程會直接從 GitHub 同步。

## 快速開始

### 1. Clone repo

```bash
git clone https://github.com/edward-playground/aidefend-mcp.git
cd aidefend-mcp
```

### 2. 選一種安裝路徑

| 使用情境 | 建議指令 |
| --- | --- |
| Claude Desktop MCP | `python scripts/install.py` |
| Claude Code MCP | `python scripts/install.py --client code` |
| 只用 REST API | `python scripts/install.py --no-mcp` |
| 手動安裝 | 參考 [INSTALL-繁體中文.md](INSTALL-繁體中文.md) |

### 3. 建立本地知識庫

```bash
python __main__.py --resync
```

第一次同步會下載 framework、embedding model，並建立本地資料庫。乾淨環境下通常需要幾分鐘。

### 4. 啟動服務

REST API：

```bash
python __main__.py
```

MCP server：

```bash
python __main__.py --mcp
```

健康檢查：

```bash
curl http://127.0.0.1:8000/health
```

## 從乾淨環境手動安裝

如果你不想用安裝腳本，而是想走明確的手動流程：

```bash
python -m venv .venv
```

啟用虛擬環境。

Windows PowerShell：

```powershell
.venv\Scripts\Activate.ps1
```

macOS / Linux：

```bash
source .venv/bin/activate
```

安裝依賴：

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

安全 JavaScript parser 使用 `vendor/` 內隨附的 Acorn runtime，因此這個流程
不會下載 Node 套件，也不需要 `npm`。

建立本地設定檔：

macOS / Linux：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

然後執行：

```bash
python __main__.py --resync
python __main__.py
```

## 可選的本機 framework 覆寫

預設情況下服務會從 GitHub 同步。如果你同時在本機開發 `aidefense-framework`，可以把同步來源切到本機：

```env
LOCAL_FRAMEWORK_PATH=/path/to/aidefense-framework
```

這是可選設定。對一般開源使用者來說，應該保持未設定。

## 常用指令

```bash
# 依照目前設定的來源重建本地資料庫
python __main__.py --resync

# 啟動 REST API
python __main__.py

# 啟動 MCP server
python __main__.py --mcp

# 執行測試 / 靜態掃描（請先安裝開發相依套件）
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m bandit -q -r app
```

## Docker

容器會綁定 `0.0.0.0`，因此必須設定 API 金鑰（未設定時 compose 會拒絕啟動）：

```bash
# 1. 建立 .env 並產生 REST API 金鑰
cp .env.example .env
python scripts/generate_api_key.py     # 將產生的值填入 .env 的 AIDEFEND_API_KEY

# 2. 啟動
docker compose up -d
```

驗證細節請參考 [docs/CONFIGURATION.md](docs/CONFIGURATION.md)。

## 文件

- 安裝： [INSTALL-繁體中文.md](INSTALL-繁體中文.md)
- 設定： [docs/CONFIGURATION.md](docs/CONFIGURATION.md)
- 進階設定： [docs/ADVANCED_CONFIGURATION.md](docs/ADVANCED_CONFIGURATION.md)
- 工具說明： [docs/TOOLS-繁體中文.md](docs/TOOLS-繁體中文.md)
- 安全說明： [SECURITY.md](SECURITY.md)
- 變更記錄： [CHANGELOG.md](CHANGELOG.md)

## Repo 說明

- 從 source checkout 執行時，runtime data 放在 repo 的 `data/`；wheel
  安裝則使用作業系統的使用者資料目錄，Docker 固定使用 `/app/data`。
- CI 會建立並逐筆驗證最新 upstream index；在 Linux 上，會分別從 source
  checkout 與 repo 外安裝的 wheel 跑完 18 個 MCP 及 18 個 REST tool path。
  Windows、macOS、Linux 與 Python 3.10-3.13 matrix 則驗證乾淨 wheel 安裝、
  parser 與 console 契約，另有 Bandit、實際 container build/runtime 契約，
  以及每天驗證最新公開 framework 的 rolling upstream canary。
- Source contract 會從 framework 的 `main.js` manifest 動態取得有順序的
  tactic 檔案集合，不會把 runtime 綁死在目前七個檔名或標題。
- 目前 release contract 已對齊 AIDEFEND **1.20260724**、authoring schema
  **1.7**、public schema **2.3** 與 index schema **3.2**。這是精確驗證快照，
  不是對未來 framework ID、標題、內容、筆數或順序的固定限制。

## 授權

MIT，詳見 [LICENSE](LICENSE)。
