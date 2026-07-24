[English Installation Guide](INSTALL.md) | [繁體中文安裝指南](INSTALL-繁體中文.md)

---

# 安裝指南

這份指南是以「剛從 GitHub clone 下來的陌生使用者」為前提寫的。

如果你只需要最短可跑通路徑：

```bash
git clone https://github.com/edward-playground/aidefend-mcp.git
cd aidefend-mcp
python scripts/install.py --no-mcp
python __main__.py --resync
python __main__.py
```

如果你要整合 Claude Desktop，就把上面的安裝指令改成 `python scripts/install.py`。

## 先選一條路徑

| 目標 | 建議路徑 |
| --- | --- |
| Claude Desktop MCP | `python scripts/install.py` |
| Claude Code MCP | `python scripts/install.py --client code` |
| 只用 REST API | `python scripts/install.py --no-mcp` |
| 想完全手動控制 | 走下面的手動安裝 |
| 容器化部署 | 使用 Docker Compose |

## 前置需求

- Python 3.10 到 3.13
- Node.js 18+
- Git
- 2 到 3 GB 可用磁碟空間

不需要 `npm`。Repository 已隨附 Acorn parser runtime；只有執行 parser 檢查
與解析 framework 資料時需要 Node.js 18+。

先確認版本：

```bash
python --version
node --version
git --version
```

## 建議路徑：安裝腳本

先 clone repo：

```bash
git clone https://github.com/edward-playground/aidefend-mcp.git
cd aidefend-mcp
```

然後選一個：

```bash
# Claude Desktop
python scripts/install.py

# Claude Code
python scripts/install.py --client code

# 只用 REST API
python scripts/install.py --no-mcp
```

安裝完成後，先建立本地資料庫：

```bash
python __main__.py --resync
```

接著啟動：

```bash
# REST API
python __main__.py

# MCP server
python __main__.py --mcp
```

## 手動安裝

### 1. Clone repo

```bash
git clone https://github.com/edward-playground/aidefend-mcp.git
cd aidefend-mcp
```

### 2. 建立虛擬環境

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

### 3. 安裝 Python 依賴

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

安全 JavaScript parser 使用 repository 內隨附的 Acorn runtime。安裝器會驗證這些
本機 parser 檔案，不會執行 `npm`，JavaScript 依賴檢查也不需要網路；執行時仍需
確保 Node.js 18+ 可用。

### 4. 建立本地設定檔

macOS / Linux：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

一般使用者可以直接保留預設值。服務預設會從 GitHub 同步。

### 5. 建立知識庫

```bash
python __main__.py --resync
```

第一次執行會下載 framework 與 embedding model，並在本地建立 LanceDB，通常要幾分鐘。

### 6. 啟動服務

REST API：

```bash
python __main__.py
```

MCP：

```bash
python __main__.py --mcp
```

### 7. 驗證服務

REST 健康檢查：

```bash
curl http://127.0.0.1:8000/health
```

API 文件：

```text
http://127.0.0.1:8000/docs
```

## Docker Compose

容器會綁定 `0.0.0.0`，因此必須設定 API 金鑰（未設定時 compose 會拒絕啟動）：

```bash
# 1. 建立 .env 並產生 REST API 金鑰
cp .env.example .env
python scripts/generate_api_key.py     # 將產生的值填入 .env 的 AIDEFEND_API_KEY

# 2. 啟動
docker compose up -d
```

驗證細節請參考 [docs/CONFIGURATION.md](docs/CONFIGURATION.md)。

## 可選的本機 framework 來源

預設同步來源是 GitHub 上游 repo。

若不是使用容器，而是直接在本機執行服務，可將設定指向本機 checkout：

```env
LOCAL_FRAMEWORK_PATH=/path/to/aidefense-framework
```

標準開源安裝請保持未設定。

使用 Docker 時，主機路徑無法直接當成 Linux 容器內的路徑。請把 framework
checkout 以唯讀方式掛載到 `/framework`，並將設定指向這個容器路徑。以下假設
兩個 repo 位於同一層目錄；先以本機來源重建持久化索引，再使用同一個 data
volume 啟動 REST 服務。

macOS / Linux：

```bash
docker compose run --rm \
  --env LOCAL_FRAMEWORK_PATH=/framework \
  --volume ../aidefense-framework:/framework:ro \
  aidefend-mcp python __main__.py --resync

docker compose run --rm --service-ports \
  --env LOCAL_FRAMEWORK_PATH=/framework \
  --volume ../aidefense-framework:/framework:ro \
  aidefend-mcp
```

Windows PowerShell：

```powershell
docker compose run --rm `
  --env LOCAL_FRAMEWORK_PATH=/framework `
  --volume ../aidefense-framework:/framework:ro `
  aidefend-mcp python __main__.py --resync

docker compose run --rm --service-ports `
  --env LOCAL_FRAMEWORK_PATH=/framework `
  --volume ../aidefense-framework:/framework:ro `
  aidefend-mcp
```

若 framework 不在相鄰目錄，請替換 volume 參數左側的主機路徑；容器內路徑仍
保持 `/framework`，並保留唯讀掛載。Compose 會把 `.env` 的其餘設定傳入容器；
一般執行 `docker compose up` 時會刻意清除主機版 `LOCAL_FRAMEWORK_PATH`，只會在
上述指令已掛載 `/framework` 後才安全覆寫。容器仍以明確的網路與驗證設定
強制使用 `0.0.0.0` 及 API 金鑰驗證。

## 常用指令

```bash
# 依照目前設定的來源重建資料庫
python __main__.py --resync

# 執行測試 / Bandit（請先安裝開發相依套件）
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m bandit -q -r app
```

## 常見問題

- 找不到 `node`：請安裝 Node.js 18+，並確認 `node --version` 可執行。
- Windows 上 ONNX 或 runtime 出錯：請安裝 Microsoft Visual C++ Redistributable。
- 第一次 sync 很慢：這是正常現象，因為會下載 model 與 framework 資料。
- 綁外部介面但沒有 auth 會啟動失敗：這是刻意的安全限制，不是 bug。

## 更多文件

- 總覽： [README-繁體中文.md](README-繁體中文.md)
- 設定： [docs/CONFIGURATION.md](docs/CONFIGURATION.md)
- 進階設定： [docs/ADVANCED_CONFIGURATION.md](docs/ADVANCED_CONFIGURATION.md)
- 安全： [SECURITY.md](SECURITY.md)
