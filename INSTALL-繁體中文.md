[English Installation Guide](INSTALL.md) | [繁體中文安裝指南](INSTALL-繁體中文.md)

---

# 安裝指南

**AIDEFEND MCP Service 完整的逐步安裝指南**

本指南每個步驟都有詳細說明。如果遇到問題，請查看[疑難排解](#疑難排解常見問題)章節。

---

## 📋 目錄

1. [你需要準備什麼（前置需求）](#你需要準備什麼前置需求)
2. [方法 1: 使用腳本快速開始（最簡單）](#方法-1-使用腳本快速開始最簡單)
3. [方法 2: Docker 安裝（建議用於正式環境）](#方法-2-docker-安裝建議用於正式環境)
4. [方法 3: 手動安裝](#方法-3-手動安裝)
5. [驗證一切正常運作](#驗證一切正常運作)
6. [疑難排解常見問題](#疑難排解常見問題)
7. [下一步](#下一步)

---

## 你需要準備什麼（前置需求）

在安裝之前，請確保你的電腦上已安裝這些:

### ✅ 必要軟體

#### 1. **Python 3.9 或更高版本**

**什麼是 Python？** 一種程式語言。這個服務是用 Python 寫的。

**檢查你是否已安裝：**
```bash
python --version
```

**預期輸出：** `Python 3.9.x` 或更高版本（例如 `Python 3.11.5`）

**還沒安裝？** 請從這裡下載：https://www.python.org/downloads/

**安裝提示：**
- **Windows**: 安裝時請勾選「Add Python to PATH」
- **macOS**: 使用安裝程式或 `brew install python`
- **Linux**: 通常已預裝，或執行 `sudo apt install python3`

---

#### 2. **Git**（用於下載程式碼）

**什麼是 Git？** 一個從 GitHub 下載程式碼的工具。

**檢查你是否已安裝：**
```bash
git --version
```

**預期輸出：** `git version 2.x.x`

**還沒安裝？** 請從這裡下載：https://git-scm.com/

---

### 🐳 選配：Docker（用於容器化部署）

**什麼是 Docker？** 一個將服務及其所有相依套件打包成「容器」的工具 - 可以想像成一個可攜帶的、隔離的環境。

**何時使用 Docker：**
- 你想要最簡單的安裝（不需要設定 Python）
- 你要部署到正式環境
- 統一化 - 避免「(只有)在我的機器上可以跑」的問題

**檢查你是否已安裝：**
```bash
docker --version
docker-compose --version
```

**還沒安裝？** 請下載 **Docker Desktop**：https://www.docker.com/products/docker-desktop/

---

### 💻 系統需求

- **RAM**: 最低 2GB，建議 4GB
- **磁碟空間**: 500MB 可用空間（用於 ML models 和 AIDEFEND 內容）
- **網路**: 初次下載時需要（設定後可離線運作）

---

## 方法 1: 使用腳本快速開始（最簡單）

**建議對象：** 第一次使用的人、本地開發

這個方法使用我們的自動化腳本來處理所有事情。

### 步驟 1: 下載程式碼

開啟你的終端機（Windows 上是 Command Prompt，macOS/Linux 上是 Terminal）並執行：

```bash
git clone https://github.com/edward-playground/aidefend-mcp.git
cd aidefend-mcp
```

**這會做什麼：**
- 下載所有程式碼到一個叫 `aidefend-mcp` 的資料夾
- 切換到那個資料夾

**確認你在正確的位置：**
```bash
# 你應該會看到 README.md、start.sh、start.bat 等檔案
ls  # macOS/Linux
dir # Windows
```

---

### 步驟 2: 執行啟動腳本

**在 Windows 上：**
```cmd
start.bat
```

**在 macOS/Linux 上：**
```bash
chmod +x start.sh
./start.sh
```

**這個腳本會自動做什麼：**
1. ✅ 檢查 Python 是否已安裝
2. ✅ 建立 virtual environment（隔離的 Python 環境）
3. ✅ 安裝所有必要的 Python 套件
4. ✅ 建立設定檔（`.env`）
5. ✅ 啟動服務

**預期輸出：**
```
==========================================
AIDEFEND MCP Service - Quick Start
==========================================

Checking Python version...
+ Python OK
Creating virtual environment...
+ Virtual environment created
Installing dependencies (this may take a few minutes)...
+ Dependencies installed

==========================================
Starting AIDEFEND MCP Service...
==========================================

The service will:
  1. Download AIDEFEND framework from GitHub
  2. Parse and index the content
  3. Start the API server on http://localhost:8000

This may take a few minutes on first run...

INFO - Starting AIDEFEND sync process
INFO - Downloading tactics files...
INFO - Parsing JavaScript files...
INFO - Embedding 1250 documents... (this is the slow part)
INFO - Indexing in vector database...
INFO - Sync complete!
INFO - QueryEngine initialized successfully
INFO - Application startup complete
INFO - Uvicorn running on http://127.0.0.1:8000
```

**第一次安裝：**「Embedding documents」這個步驟需要 **1-3 分鐘**（下載輕量級 ONNX models）。這是正常的！

---

### 步驟 3: 測試服務

**開啟一個新的終端機**（讓服務在第一個終端機繼續執行）並執行：

```bash
curl http://localhost:8000/health
```

**預期回應：**
```json
{
  "status": "healthy",
  "checks": {
    "database": true,
    "embedding_model": true,
    "sync_service": true
  }
}
```

**✅ 成功！** 你的服務正在執行。

**繼續前往：** [驗證一切正常運作](#驗證一切正常運作)

---

## 方法 2: Docker 安裝（建議用於正式環境）

**建議對象：** 正式環境部署、輕鬆更新、可重現的環境

### Docker 方法的前置需求

確保 Docker Desktop 已安裝並正在執行：
```bash
docker --version
docker-compose --version
```

---

### 步驟 1: 下載程式碼

```bash
git clone https://github.com/edward-playground/aidefend-mcp.git
cd aidefend-mcp
```

---

### 步驟 2:（選配）自訂設定

如果你想修改設定（port 號碼、同步頻率等）：

```bash
# 複製範例設定檔
cp .env.example .env

# 用你的文字編輯器編輯
notepad .env      # Windows
nano .env         # Linux
open -e .env      # macOS
```

**對大多數使用者來說，預設值就可以了。你可以跳過這個步驟。**

---

### 步驟 3: 使用 Docker Compose 啟動

```bash
docker-compose up -d
```

**這會做什麼：**
- `-d` 表示「detached」（在背景執行）
- 建立 Docker image（第一次需要 2-3 分鐘）
- 如需要會下載 Python
- 啟動服務
- 建立持久化的 data volume

**預期輸出：**
```
Creating network "aidefend-mcp_default" ... done
Creating volume "aidefend-mcp_aidefend-data" ... done
Building aidefend-mcp
[+] Building 125.3s (18/18) FINISHED
Creating aidefend-mcp ... done
```

---

### 步驟 4: 查看日誌

```bash
docker-compose logs -f
```

**要找什麼：**
```
aidefend-mcp    | INFO - Starting AIDEFEND sync process
aidefend-mcp    | INFO - Downloading tactics files...
aidefend-mcp    | INFO - Embedding 1250 documents...
aidefend-mcp    | INFO - Sync complete!
aidefend-mcp    | INFO - QueryEngine initialized successfully
aidefend-mcp    | INFO - Uvicorn running on http://0.0.0.0:8000
```

**按 `Ctrl+C` 離開日誌。** container 會繼續在背景執行。

---

### 步驟 5: 測試服務

```bash
curl http://localhost:8000/health
```

**預期回應：**
```json
{"status": "healthy", "checks": {"database": true, "embedding_model": true, "sync_service": true}}
```

---

### 實用的 Docker 指令

```bash
# 查看日誌
docker-compose logs -f

# 停止服務
docker-compose down

# 啟動服務
docker-compose up -d

# 重新啟動服務
docker-compose restart

# 移除所有東西並重新開始
docker-compose down -v
docker-compose up -d
```

---

## 方法 3: 手動安裝

**建議對象：** 開發者、客製化需求、想了解運作原理、進階使用者

### 步驟 1: 下載程式碼

```bash
git clone https://github.com/edward-playground/aidefend-mcp.git
cd aidefend-mcp
```

---

### 步驟 2: 建立 Virtual Environment

**什麼是 virtual environment？** 一個專為這個專案隔離的 Python 環境。它可以防止與其他 Python 專案產生衝突。

**在 Windows 上：**
```cmd
python -m venv venv
venv\Scripts\activate
```

**在 macOS/Linux 上：**
```bash
python3 -m venv venv
source venv/bin/activate
```

**如何確認成功了：**
你的終端機提示符號現在應該會以 `(venv)` 開頭：
```
(venv) C:\Users\YourName\aidefend-mcp>
```

---

### 步驟 3: 安裝 Python 相依套件

```bash
pip install -r requirements.txt
```

**這會安裝什麼：**
- FastAPI（web framework）
- LanceDB（vector database）
- FastEmbed（輕量級 ONNX-based ML model，用於 embeddings）
- 15+ 個其他套件

**第一次執行時需要 2-5 分鐘**（下載 ML models ~100MB）。

**預期輸出：**
```
Collecting fastapi==0.109.2
Downloading fastapi-0.109.2-py3-none-any.whl (92 kB)
...
Installing collected packages: ...
Successfully installed fastapi-0.109.2 ...
```

---

### 步驟 4: 建立設定檔

```bash
cp .env.example .env
```

**`.env` 裡面有什麼？** 設定項目，例如：
- Port 號碼（預設：8000）
- 同步頻率（預設：每小時）
- 流量限制（預設：每分鐘 60 次請求）

**第一次設定時，你不需要編輯這個檔案。**

---

### 步驟 5: 啟動服務

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**這個指令的意思：**
- `python -m uvicorn` - 執行 Uvicorn web server
- `app.main:app` - 從 `app/main.py` 載入 app
- `--host 127.0.0.1` - 只接受本地端連線（安全）
- `--port 8000` - 在 port 8000 執行

**預期輸出：**
```
INFO - Starting AIDEFEND sync process
INFO - Downloading tactics/harden.js...
INFO - Downloading tactics/protect.js...
INFO - Parsing JavaScript files...
INFO - Embedding 1250 documents...
INFO - Indexing in LanceDB...
INFO - Sync complete! Updated to commit abc1234
INFO - QueryEngine initialized successfully
INFO - Started server process [12345]
INFO - Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

**⏳ 第一次執行需要 1-3 分鐘** 來下載並 embedding AIDEFEND 內容。

---

## 驗證一切正常運作

服務執行後，用這些指令來測試。

### 測試 1: Health Check

```bash
curl http://localhost:8000/health
```

**預期回應：**
```json
{
  "status": "healthy",
  "checks": {
    "database": true,
    "embedding_model": true,
    "sync_service": true
  }
}
```

**❌ 如果你遇到錯誤：** 服務可能還在啟動中。等 1 分鐘後再試一次。

---

### 測試 2: 檢查同步狀態

```bash
curl http://localhost:8000/api/v1/status
```

**預期回應：**
```json
{
  "status": "online",
  "sync_info": {
    "last_synced_at": "2025-11-09T10:00:00Z",
    "current_commit_sha": "abc123...",
    "total_documents": 1250,
    "is_syncing": false
  },
  "message": "Service is online and synchronized",
  "version": "1.0.0"
}
```

**要檢查的項目：**
- ✅ `"status": "online"`
- ✅ `"is_syncing": false`
- ✅ `"total_documents": 1250`（或類似的數字）

---

### 測試 3: 嘗試真實的查詢

**使用 curl：**
```bash
curl -X POST "http://localhost:8000/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query_text": "如何防護 prompt injection？",
    "top_k": 3
  }'
```

**預期回應：** 包含與 prompt injection 相關的 AIDEFEND 技術的 JSON。

**沒有 curl？** 用瀏覽器開啟：

**http://localhost:8000/docs**

這會開啟 **Swagger UI** - 一個互動式 API 遊樂場，你可以用漂亮的 GUI 測試查詢。

---

### 測試 4: 互動式 API 文件

**在瀏覽器開啟：**
```
http://localhost:8000/docs
```

**你會看到什麼：**
- 所有 API endpoints 列表
- 「Try it out」按鈕來測試查詢
- 自動產生的文件

**試試看：**
1. 點選 `POST /api/v1/query`
2. 點選「Try it out」
3. 編輯請求本體：
   ```json
   {
     "query_text": "如何防禦 model poisoning？",
     "top_k": 5
   }
   ```
4. 點選「Execute」
5. 看結果！

---

## 設定 Claude Desktop 的 MCP 模式

**什麼是 MCP 模式？** MCP (Model Context Protocol) 讓 Claude Desktop 能將 AIDEFEND 當作工具使用。不需要複製貼上防禦戰術，Claude 可以在對話中直接搜尋知識庫。

**何時使用 MCP 模式：**
- 你希望 Claude Desktop 自動存取 AIDEFEND 知識
- 你正在進行 AI 輔助的安全對話
- 你偏好基於工具的整合而非 HTTP API

**何時改用 REST API 模式：**
- 你要與自訂應用程式整合
- 你需要 HTTP endpoints
- 你正在建立自動化腳本

---

### MCP 模式的前置需求

✅ 你已完成上述其中一種安裝方法
✅ 你已安裝 [Claude Desktop](https://claude.ai/download)
✅ AIDEFEND 服務已安裝（設定時不需要執行）

---

### 步驟 1：找到 Claude Desktop 設定檔

Claude Desktop 將 MCP server 設定儲存在 JSON 檔案中：

**macOS:**
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

**Windows:**
```
%APPDATA%\Claude\claude_desktop_config.json
```

**如何開啟它：**

#### macOS:
```bash
# 用預設文字編輯器開啟
open ~/Library/Application\ Support/Claude/claude_desktop_config.json

# 或在終端機使用 nano
nano ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

#### Windows:
```cmd
# 用記事本開啟
notepad %APPDATA%\Claude\claude_desktop_config.json
```

**檔案不存在？** 手動建立它 - 如果這是你的第一個 MCP server，這是正常的。

---

### 步驟 2：加入 AIDEFEND 設定

將此設定加入檔案中。如果檔案是空的，複製下面全部內容。如果你已經設定了其他 MCP servers，只需在現有的 `"mcpServers"` 物件內加入 `"aidefend"` 區段。

**範本：**
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
      "cwd": "/REPLACE/WITH/YOUR/PATH/TO/aidefend-mcp"
    }
  }
}
```

**⚠️ 重要：** 將 `/REPLACE/WITH/YOUR/PATH/TO/aidefend-mcp` 替換為你安裝 AIDEFEND 的**絕對路徑**。

**如何找到你的路徑：**

**macOS/Linux:**
```bash
cd /path/to/aidefend-mcp
pwd
```
複製輸出結果（例如：`/Users/yourname/projects/aidefend-mcp`）

**Windows:**
```cmd
cd C:\path\to\aidefend-mcp
cd
```
複製輸出結果，但在 JSON 檔案中**使用正斜線**：
- ✅ 正確：`"cwd": "C:/Users/YourName/projects/aidefend-mcp"`
- ❌ 錯誤：`"cwd": "C:\\Users\\YourName\\projects\\aidefend-mcp"`

---

### 步驟 3：設定範例

**範例 1：macOS 安裝**
```json
{
  "mcpServers": {
    "aidefend": {
      "command": "python",
      "args": ["-m", "aidefend_mcp", "--mcp"],
      "cwd": "/Users/alice/projects/aidefend-mcp"
    }
  }
}
```

**範例 2：Windows 安裝**
```json
{
  "mcpServers": {
    "aidefend": {
      "command": "python",
      "args": ["-m", "aidefend_mcp", "--mcp"],
      "cwd": "C:/Users/Bob/Documents/aidefend-mcp"
    }
  }
}
```

**範例 3：多個 MCP Servers**

如果你已經有其他 MCP servers（如 filesystem 或 git），將 AIDEFEND 加在旁邊：

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/alice/Documents"]
    },
    "aidefend": {
      "command": "python",
      "args": ["-m", "aidefend_mcp", "--mcp"],
      "cwd": "/Users/alice/projects/aidefend-mcp"
    }
  }
}
```

---

### 步驟 4：重新啟動 Claude Desktop

1. **完全退出 Claude Desktop**（不只是關閉視窗）
   - macOS：`Cmd+Q` 或右鍵圖示 → 結束
   - Windows：右鍵工作列圖示 → 結束

2. **重新開啟 Claude Desktop**

3. **尋找 🔌 圖示**（在 Claude 介面中）
   - 點擊它查看可用工具
   - 你應該會看到「aidefend」列在其中

---

### 步驟 5：測試 MCP 整合

在 Claude Desktop 中試試這些範例提示：

**測試 1：基本查詢**
```
可以搜尋 AIDEFEND 中關於 prompt injection 的防禦手法嗎？
```

Claude 應該會自動使用 `query_aidefend` 工具並回傳相關的防禦戰術。

**測試 2：檢查狀態**
```
AIDEFEND 知識庫的狀態如何？
```

Claude 應該會使用 `get_aidefend_status` 並回報文件數量和同步狀態。

**測試 3：手動同步**
```
請從 GitHub 同步最新的 AIDEFEND 戰術。
```

Claude 應該會使用 `sync_aidefend` 來更新知識庫。

---

### 步驟 6：了解工具

Claude Desktop 現在可以存取三個 AIDEFEND 工具：

| 工具名稱 | 功能 | 範例用法 |
|-----------|--------------|-------------|
| `query_aidefend` | 搜尋 AIDEFEND 知識庫 | 「找出 model poisoning 的防禦手法」 |
| `get_aidefend_status` | 檢查服務是否就緒並已同步 | 「AIDEFEND 是最新的嗎？」 |
| `sync_aidefend` | 手動更新知識庫 | 「同步最新的 AIDEFEND 戰術」 |

Claude 會根據你的問題自動選擇要使用哪個工具。

---

### MCP 模式疑難排解

#### ❌ Claude Desktop 沒有顯示 🔌 圖示

**可能原因：**
1. 設定檔有語法錯誤
2. AIDEFEND 的路徑不正確
3. Claude Desktop 沒有完全重新啟動

**解決方法：**
1. **驗證 JSON 語法** - 使用 https://jsonlint.com/ 檢查你的設定檔
2. **檢查路徑是絕對路徑** - 必須以 `/`（macOS/Linux）或 `C:/`（Windows）開頭
3. **Windows 使用正斜線** - 雖然 Windows 使用 `\`，但 JSON 需要 `/`
4. **完全退出 Claude** - 使用 Cmd+Q（macOS）或從工作列結束（Windows）

---

#### ❌ 工具出現但給出「Connection failed」錯誤

**原因：** AIDEFEND 服務程式碼有問題或缺少依賴套件。

**解決方法：**
1. **手動測試服務：**
   ```bash
   cd /path/to/aidefend-mcp
   python -m aidefend_mcp --mcp
   ```

   你應該會看到：`Waiting for MCP client connections...`

2. **檢查 Python 錯誤** - 如果看到錯誤訊息，服務需要修復

3. **確認已安裝依賴套件：**
   ```bash
   pip install -r requirements.txt
   ```

---

#### ❌ 第一次查詢需要 2-3 分鐘

**這是正常的！** 第一次查詢會觸發：
1. 初始與 GitHub 同步（下載 AIDEFEND 戰術）
2. 解析所有 JavaScript 檔案
3. 產生 embeddings
4. 建立 vector database

**初始同步之後**，查詢只需不到 1 秒。

**提示：** 在使用 Claude 之前先執行手動同步：
```bash
python -m aidefend_mcp  # 以 API 模式啟動
# 造訪 http://localhost:8000/api/v1/status 檢查同步狀態
```

---

#### ❌ 「Database sync in progress」錯誤

**原因：** 你在背景同步執行時進行查詢。

**解決方法：** 等待 30 秒後再試一次。這是為了保護同步期間的資料不受損壞。

---

### 同時使用 REST API 和 MCP 模式

**可以同時使用兩者嗎？** 可以！它們是完全獨立的：

- **MCP 模式**：用於 Claude Desktop 對話
- **REST API 模式**：用於 HTTP 整合、腳本、其他應用程式

**同時執行兩者：**

終端機 1：
```bash
python -m aidefend_mcp          # REST API 在 http://localhost:8000
```

終端機 2：
```bash
# 如上所示設定 Claude Desktop 的 MCP 模式
# 當 Claude Desktop 連線時，MCP 會自動執行
```

兩種模式共享相同的知識庫和同步服務 - 它們會自動保持同步。

---

## 疑難排解常見問題

### ❌ 問題：「Python not found」或「python: command not found」

**可能原因：**
1. Python 沒有安裝
2. Python 不在你的系統 PATH 中

**解決方案：**

**Windows：**
1. 從 https://www.python.org/downloads/ 重新安裝 Python
2. **重要：** 安裝時勾選「Add Python to PATH」
3. 重新啟動 Command Prompt

**macOS/Linux：**
```bash
# 試試 python3 而不是 python
python3 --version

# 如果有用，所有指令都用 python3
python3 -m venv venv
```

---

### ❌ 問題：「pip: command not found」

**macOS/Linux 解決方案：**
```bash
# 用 pip3 代替
pip3 install -r requirements.txt
```

**Windows 解決方案：**
```cmd
# 用 python -m pip
python -m pip install -r requirements.txt
```

---

### ❌ 問題：「Address already in use」或「Port 8000 is already allocated」

**意思：** 另一個程式正在使用 port 8000。

**解決方案 1: 找到並停止另一個程式**

**Windows：**
```cmd
netstat -ano | findstr :8000
taskkill /PID <上面指令得到的PID> /F
```

**macOS/Linux：**
```bash
lsof -i :8000
kill -9 <上面指令得到的PID>
```

**解決方案 2: 使用不同的 port**

編輯 `.env`：
```env
API_PORT=8001
```

或用不同 port 執行：
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

---

### ❌ 問題：服務啟動了但查詢回傳「503 Service Not Ready」

**意思：** 初次同步還在執行中。

**解決方案：** 等待 1-3 分鐘讓 embedding 程序完成。

**檢查同步狀態：**
```bash
curl http://localhost:8000/api/v1/status
```

**找找看：**
```json
{
  "sync_info": {
    "is_syncing": true  ← 還在同步中，請等待
  }
}
```

**如果 `is_syncing` 卡在 `true` 超過 10 分鐘：**

1. 檢查日誌：`tail -f data/logs/aidefend_mcp.log`
2. 檢查網路連線：`curl https://api.github.com`
3. 重新啟動服務

---

### ❌ 問題：「ModuleNotFoundError: No module named 'fastapi'」

**意思：** 相依套件沒有安裝，或 virtual environment 沒有啟動。

**解決方案：**

1. **啟動 virtual environment：**
   ```bash
   # Windows
   venv\Scripts\activate

   # macOS/Linux
   source venv/bin/activate
   ```

2. **重新安裝相依套件：**
   ```bash
   pip install -r requirements.txt
   ```

---

### ❌ 問題：Docker container 一直重新啟動

**檢查日誌：**
```bash
docker-compose logs aidefend-mcp
```

**常見原因：**

1. **記憶體不足：**
   - 開啟 Docker Desktop → Settings → Resources
   - 將記憶體增加到至少 2GB

2. **網路問題：**
   - 檢查網路連線
   - 確認可存取 GitHub：`curl https://api.github.com`

3. **Port 衝突：**
   - 另一個服務正在使用 port 8000
   - 在 `docker-compose.yml` 修改：`"8001:8000"`

---

### ❌ 問題：Embedding 程序非常慢（>10 分鐘）

**第一次執行是正常的：** 約 1250 個文件需要 1-3 分鐘

**如果花更久時間：**

**可能原因：**
1. **網路慢** - 正在下載 ML models（~100MB）
2. **CPU 慢** - embedding 是會耗用大量 CPU 資源的
3. **RAM 不足** - 系統正在同時跑其他服務

**解決方案：**
1. **檢查下載速度：** 造訪 https://fast.com
2. **關閉其他程式** 釋放 CPU/RAM
3. **耐心等待** - 只有第一次執行會這樣
4. **對於非常慢的機器：** 考慮使用雲端伺服器

---

### ❌ 問題：「Permission denied」（Linux/macOS）

**對於 start.sh：**
```bash
chmod +x start.sh
./start.sh
```

**對於 data 目錄：**
```bash
chmod -R 755 data/
```

---

### ❌ 問題：curl 指令在 Windows 上不能用

**解決方案 1: 用 PowerShell 代替 Command Prompt**

PowerShell 內建 curl。

**解決方案 2: 用瀏覽器**

前往 http://localhost:8000/docs 並使用互動式 UI。

**解決方案 3: 安裝 Windows 版 curl**

從這裡下載：https://curl.se/windows/

---

## 下一步

### 🎉 恭喜！你的服務已成功執行。

**接下來該做什麼：**

1. **閱讀 API 文件**
   - 開啟 http://localhost:8000/docs
   - 嘗試不同的查詢
   - 看看回傳什麼資料

2. **與你的 LLM 整合**
   - 使用 `/api/v1/query` endpoint
   - 傳送使用者的問題
   - 取得相關的 AIDEFEND context
   - 將 context 傳給你的 LLM（GPT-4、Claude 等）

3. **自訂設定**
   - 編輯 `.env` 修改設定
   - 調整流量限制
   - 變更同步頻率

4. **學習更多**
   - 閱讀 [README.md](README.md) 取得 API 使用範例
   - 查看 [SECURITY.md](SECURITY.md) 了解部署最佳實踐

---

## 取得協助

**如果你還是卡住了：**

1. **檢查現有 issues：** https://github.com/edward-playground/aidefend-mcp/issues
2. **搜尋 discussions：** https://github.com/edward-playground/aidefend-mcp/discussions
3. **建立新的 issue** 並包含：
   - 你的作業系統（Windows 11、macOS 14、Ubuntu 22.04 等）
   - Python 版本：`python --version`
   - 完整的錯誤訊息（複製貼上）
   - 你嘗試過什麼
   - 相關的日誌檔案

---

## 解除安裝

**本地端安裝：**
```bash
# 停止服務（Ctrl+C）

# 停用 virtual environment
deactivate

# 移除所有東西
cd ..
rm -rf aidefend-mcp  # macOS/Linux
rd /s aidefend-mcp   # Windows
```

**Docker 安裝：**
```bash
# 停止並移除所有東西
docker-compose down -v

# 移除目錄
cd ..
rm -rf aidefend-mcp
```

---

**有問題？Issues？功能請求？**

開啟 issue：https://github.com/edward-playground/aidefend-mcp/issues

**祝你部署順利！🚀**
