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

- Python 3.9 到 3.13
- Node.js 18+
- Git
- 2 到 3 GB 可用磁碟空間

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

### 3. 安裝 Python 與 Node 依賴

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
npm ci
```

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

```bash
docker-compose up -d
```

如果你要綁定 `0.0.0.0`，就必須開啟驗證。請參考 [docs/CONFIGURATION.md](docs/CONFIGURATION.md)。

## 可選的本機 framework 來源

預設同步來源是 GitHub 上游 repo。

如果你正在本機開發 `aidefense-framework`，希望這個服務直接索引你的本機 checkout，可以設定：

```env
LOCAL_FRAMEWORK_PATH=/path/to/aidefense-framework
```

標準開源安裝請保持未設定。

## 常用指令

```bash
# 依照目前設定的來源重建資料庫
python __main__.py --resync

# 執行測試
python -m pytest -q

# 執行 Bandit
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
