[English README](README.md) | [繁體中文 README](README-繁體中文.md)

---

# AIDEFEND MCP / REST API Service

[![CI](https://github.com/edward-playground/aidefend-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/edward-playground/aidefend-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%20|%203.13-blue.svg)](https://www.python.org/downloads/)
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

## 需求

- Python 3.9 到 3.13
- Node.js 18+
- Git
- 約 2 到 3 GB 可用磁碟空間，包含依賴、embedding model 與本地資料庫

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
npm ci
```

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

# 執行測試
python -m pytest -q

# 執行靜態安全掃描
python -m bandit -q -r app
```

## Docker

```bash
docker-compose up -d
```

如果要綁定外部介面，必須開啟驗證。請參考 [docs/CONFIGURATION.md](docs/CONFIGURATION.md)。

## 文件

- 安裝： [INSTALL-繁體中文.md](INSTALL-繁體中文.md)
- 設定： [docs/CONFIGURATION.md](docs/CONFIGURATION.md)
- 進階設定： [docs/ADVANCED_CONFIGURATION.md](docs/ADVANCED_CONFIGURATION.md)
- 工具說明： [docs/TOOLS-繁體中文.md](docs/TOOLS-繁體中文.md)
- 安全說明： [SECURITY.md](SECURITY.md)
- 變更記錄： [CHANGELOG.md](CHANGELOG.md)

## Repo 說明

- `data/`、本地 cache、coverage 輸出與 `.env` 都已被 git ignore，不需要提交到 repo。
- CI 會在 push 與 pull request 上自動跑 `pytest` 與 `bandit`。
- 這個服務已針對 **2026-04-14** 的最新版 AIDEFEND framework 結構完成驗證。

## 授權

MIT，詳見 [LICENSE](LICENSE)。
