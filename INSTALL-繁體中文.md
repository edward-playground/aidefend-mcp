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

#### 2. **Node.js（任何近期版本）**

**什麼是 Node.js？** 一個 JavaScript 執行環境。我們用它來解析 AIDEFEND framework 檔案（這些檔案是用 JavaScript 寫的）。

**檢查你是否已安裝：**
```bash
node --version
```

**預期輸出：** `v18.x.x` 或更高版本（任何近期版本都可以）

**還沒安裝？** 請從這裡下載：https://nodejs.org/

**建議：** 下載「LTS」（Long Term Support，長期支援）版本以獲得穩定性。

---

#### 3. **Git**（用於下載程式碼）

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

- **RAM**: 最低 4GB，建議 8GB
- **磁碟空間**: 2GB 可用空間（用於 ML models 和 AIDEFEND 內容）
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
1. ✅ 檢查 Python 和 Node.js 是否已安裝
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
Checking Node.js...
+ Node.js OK
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
INFO - Parsing JavaScript files with Node.js...
INFO - Embedding 1250 documents... (this is the slow part)
INFO - Indexing in vector database...
INFO - Sync complete!
INFO - QueryEngine initialized successfully
INFO - Application startup complete
INFO - Uvicorn running on http://127.0.0.1:8000
```

**第一次安裝：**「Embedding documents」這個步驟需要 **2-5 分鐘**（下載 ML models）。這是正常的！

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
- 如需要會下載 Python/Node.js
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
- Sentence Transformers（用於 embeddings 的 ML model）
- 20+ 個其他套件

**第一次執行時需要 5-10 分鐘**（下載 ML models ~500MB）。

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

### 步驟 5: 確認 Node.js 可以存取

```bash
node --version
```

**如果這個指令失敗：**
1. 確保 Node.js 已安裝（參見[前置需求](#你需要準備什麼前置需求)）
2. 重新啟動你的終端機
3. 如果還是失敗，在 `.env` 設定完整路徑：

**Windows：**
```env
NODE_EXECUTABLE=C:\Program Files\nodejs\node.exe
```

**macOS/Linux：**
```env
NODE_EXECUTABLE=/usr/local/bin/node
```

要找到路徑，執行：
```bash
which node    # macOS/Linux
where node    # Windows
```

---

### 步驟 6: 啟動服務

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
INFO - Parsing JavaScript files with Node.js...
INFO - Embedding 1250 documents...
INFO - Indexing in LanceDB...
INFO - Sync complete! Updated to commit abc1234
INFO - QueryEngine initialized successfully
INFO - Started server process [12345]
INFO - Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

**⏳ 第一次執行需要 2-5 分鐘** 來下載並 embedding AIDEFEND 內容。

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

### ❌ 問題：「Node.js not found」或「node: command not found」

**解決方案：**
1. 從 https://nodejs.org/ 安裝 Node.js
2. 重新啟動你的終端機
3. 確認：`node --version`

**還是不行？**

找出 Node.js 安裝在哪裡：
```bash
# Windows
where node

# macOS/Linux
which node
```

複製路徑並加到 `.env`：
```env
NODE_EXECUTABLE=/path/to/node
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

**解決方案：** 等待 2-5 分鐘讓 embedding 程序完成。

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
   - 將記憶體增加到至少 4GB

2. **網路問題：**
   - 檢查網路連線
   - 確認可存取 GitHub：`curl https://api.github.com`

3. **Port 衝突：**
   - 另一個服務正在使用 port 8000
   - 在 `docker-compose.yml` 修改：`"8001:8000"`

---

### ❌ 問題：Embedding 程序非常慢（>10 分鐘）

**第一次執行是正常的：** 約 1250 個文件需要 2-5 分鐘

**如果花更久時間：**

**可能原因：**
1. **網路慢** - 正在下載 ML models（~500MB）
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
   - Node.js 版本：`node --version`
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
