[English Installation Guide](INSTALL.md) | [繁體中文安裝指南](INSTALL-繁體中文.md)

---

# 安裝指南

**AIDEFEND MCP Service 完整的逐步安裝指南**

本指南每個步驟都有詳細說明。如果遇到問題，請查看[疑難排解](#疑難排解常見問題)章節。

---

## 📋 目錄

1. [你需要準備什麼（前置需求）](#你需要準備什麼前置需求)
2. [🚀 MCP 模式設定（Claude Desktop）- 自動化](#-mcp-模式設定claude-desktop--自動化)
3. [方法 1: 使用腳本快速開始（最簡單）](#方法-1-使用腳本快速開始最簡單)
4. [方法 2: Docker 安裝（建議用於正式環境）](#方法-2-docker-安裝建議用於正式環境)
5. [方法 3: 手動安裝](#方法-3-手動安裝)
6. [驗證一切正常運作](#驗證一切正常運作)
7. [疑難排解常見問題](#疑難排解常見問題)
8. [下一步](#下一步)

---

## 你需要準備什麼（前置需求）

在安裝之前，請確保你的電腦上已安裝這些:

### ✅ 必要軟體

#### 1. **Python 3.9 - 3.13**

**什麼是 Python？** 一種程式語言。這個服務是用 Python 寫的。

**檢查你是否已安裝：**
```bash
python --version
```

**預期輸出：** `Python 3.9.x` 或更高版本（例如 `Python 3.11.5`、`Python 3.13.6`）

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

#### 3. **Node.js 18+**（解析 JavaScript 檔案必要）

**什麼是 Node.js？** 一個 JavaScript 執行環境，用於解析 AIDEFEND framework 中使用 JavaScript template literals 的檔案。

**檢查你是否已安裝：**
```bash
node --version
```

**預期輸出：** `v18.x.x` 或更高版本（例如 `v22.18.0`）

**還沒安裝？**

✨ **新功能：半自動安裝！** 安裝腳本現在可以自動下載並安裝 Node.js LTS：
- 自動檢測是否已安裝 Node.js >= 18
- 從 nodejs.org API 獲取最新 LTS 版本資訊
- 從 Node.js 官方網站下載安裝程式（約 30-35MB）
- 提供自動安裝選項，使用標準安裝介面
- **Windows/macOS**: 啟動安裝程式，等待完成，驗證安裝
- **Linux**: 提供針對各發行版的套件管理器指令
- 如需要可退回手動安裝指示

**運作方式：**
1. 執行 `python scripts/install.py`
2. 如果缺少 Node.js 或版本 < 18，你會看到安裝選項：
   - **[1] 自動安裝**（推薦，適用 Windows/macOS）- 自動下載並安裝
   - **[2] 顯示手動安裝指示** - 如果你偏好手動控制或在 Linux 上
   - **[3] 跳過** - 繼續執行但不安裝（稍後會失敗）
3. 選擇選項 1 即可輕鬆安裝！

**手動安裝（如果你偏好）：**
- **Windows**: 從 https://nodejs.org/ 下載（使用 LTS 版本）
- **macOS**: 從 https://nodejs.org/ 下載或使用 `brew install node`
- **Linux**: 使用套件管理器（自動安裝程式會顯示指令）

**為什麼需要這個？** AIDEFEND framework 使用 JavaScript ES6 template literals（反引號），無法單獨用 Python 解析。本服務使用 Node.js subprocess 來原生解析這些檔案。

---

#### 4. **Microsoft Visual C++ Redistributable**（僅 Windows）

**這是什麼？** Windows 上 AI/ML 程式庫所需的一組執行階段程式庫。

**誰需要它？** 僅 Windows 使用者（macOS 和 Linux 使用者可跳過此步驟）

**何時需要？** ONNX Runtime（用於嵌入向量生成）在 Windows 上需要 Visual C++ runtime DLLs。

**檢查你是否已安裝：**
- 在 Windows 設定中開啟「應用程式與功能」
- 搜尋「Microsoft Visual C++ 2015-2022 Redistributable」

**還沒安裝？**

✨ **新功能：半自動安裝！** 安裝腳本現在可以自動下載並安裝 Visual C++ Redistributable：
- 自動檢測是否已安裝（檢查 Windows registry）
- 從 Microsoft 官方網站下載安裝程式（約 14MB）
- 提供自動安裝選項，使用者互動最少
- 顯示 UAC 提示要求管理員權限（一鍵批准）
- 如需要可退回手動安裝指示

**運作方式：**
1. 執行 `python scripts/install.py`
2. 如果缺少 Visual C++，你會看到安裝選項：
   - **[1] 自動安裝**（推薦）- 自動下載並安裝
   - **[2] 顯示手動安裝指示** - 如果你偏好手動控制
   - **[3] 跳過** - 繼續執行但不安裝（稍後會失敗）
3. 選擇選項 1 即可輕鬆安裝！

**手動安裝（如果你偏好）：**
- **最新版本：** https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist
- **直接下載：** https://aka.ms/vs/17/release/vc_redist.x64.exe

**為什麼需要這個？** Python AI/ML 程式庫（如 ONNX Runtime）使用原生 C++ 程式碼以提升效能。這些程式庫需要 Visual C++ runtime DLLs 才能在 Windows 上運作。

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
- **磁碟空間**: **2-2.5GB 可用空間**（詳細分解如下）

  **AIDEFEND 服務本身 (~200-700MB):**
  - 原始碼: ~10MB
  - 向量資料庫（知識庫）: ~100-500MB（隨 AIDEFEND 框架更新而增長）
  - 原始內容快取: ~50-100MB
  - 日誌檔案: ~10-50MB

  **外部相依套件 (~1.5GB):**
  - ONNX 嵌入模型（Int8 量化版）: ~280MB
  - Python 套件（pip）: ~500MB-1GB（FastAPI、LanceDB、NumPy 等）
  - Node.js 套件（npm）: ~100-200MB（Acorn 解析器）

  **總計: 最低 2GB，資料庫增長後最多 3GB**

- **網路**: 初次下載時需要（設定後可離線運作）

---

## 🚀 MCP 模式設定（Claude Desktop）- 一鍵安裝

**適用於：想要在 Claude Desktop 中使用 AIDEFEND 的使用者**

這個一鍵安裝腳本會自動安裝所有依賴並設定 Claude Desktop，只需 2 分鐘。

### 前置需求

1. **Claude Desktop 已安裝** - 下載位置：https://claude.ai/download
2. **Python 3.9+** - 檢查：`python --version`
3. **Node.js 18+** - 檢查：`node --version`（下載：https://nodejs.org/）
4. **Git** - 檢查：`git --version`

### 步驟 1：下載 AIDEFEND

```bash
git clone https://github.com/edward-playground/aidefend-mcp.git
cd aidefend-mcp
```

**💡 提示：** macOS/Linux 使用者，如果 `python` 指向 Python 2，請使用 `python3`：
```bash
python3 --version  # 檢查是否需要使用 python3
```

### 步驟 2：（可選但建議）建立虛擬環境

使用虛擬環境可避免與其他 Python 專案的依賴衝突：

```bash
# 建立虛擬環境
python -m venv venv

# 啟動虛擬環境
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows

# 您應該會在終端機提示符看到 (venv)
```

**為什麼使用 venv？**
- 隔離 AIDEFEND 的依賴，不影響其他 Python 專案
- 避免版本衝突（例如其他專案使用不同版本的 Pydantic）
- 易於移除（只需刪除 `venv` 資料夾）

**注意：** 如果使用 venv，每次執行 AIDEFEND 前都要記得啟動它。

### 步驟 3：一鍵安裝

**建議先檢查前置需求：**
```bash
python scripts/install.py --check
```

**然後安裝：**
```bash
python scripts/install.py
```

**Linux/macOS 使用者：** 如有需要請使用 `python3`：
```bash
python3 scripts/install.py --check
python3 scripts/install.py
```

**這個腳本會：**
- ✅ 檢查 Python 3.9+ 和 Node.js 18+ 版本
- ✅ 自動安裝所有 Python 依賴（pip install -r requirements.txt）
- ✅ 自動安裝所有 Node.js 依賴（npm install）
- ✅ 自動偵測 Python 路徑和專案路徑
- ✅ 自動偵測 Claude Desktop 設定檔位置
- ✅ **安全合併**配置（保留所有現有的 MCP 工具）
- ✅ 建立現有設定的備份
- ✅ 寫入前驗證所有路徑

**範例輸出：**
```
======================================================================
  AIDEFEND MCP - 一鍵安裝
======================================================================

[步驟 1/5] 檢查 Python 版本
----------------------------------------------------------------------
   Python 版本: 3.13.1
✅ Python 版本 OK

[步驟 2/5] 檢查 Node.js 版本
----------------------------------------------------------------------
   Node.js 版本: v20.11.0
✅ Node.js 版本 OK

[步驟 3/5] 安裝 Python 依賴
----------------------------------------------------------------------
正在安裝 Python 依賴...
   使用: c:\Users\you\aidefend-mcp\requirements.txt
✅ Python 依賴安裝成功

[步驟 4/5] 安裝 Node.js 依賴
----------------------------------------------------------------------
正在安裝 Node.js 依賴...
   使用: c:\Users\you\aidefend-mcp\package.json
✅ Node.js 依賴安裝成功

[步驟 5/5] 設定 Claude Desktop（MCP 模式）
----------------------------------------------------------------------
正在設定 Claude Desktop MCP 模式...
   設定檔: C:\Users\you\AppData\Roaming\Claude\claude_desktop_config.json
   Python: C:/Python313/python.exe
   專案: c:/Users/you/aidefend-mcp

✅ 備份已建立: claude_desktop_config.json.backup.20250126_143022
✅ 保留現有的 2 個 MCP 工具：
   • filesystem
   • git
✅ 設定檔已儲存: C:\Users\you\AppData\Roaming\Claude\claude_desktop_config.json

✅ MCP 設定完成！

⚠️  重要：重新啟動 Claude Desktop 以套用變更
   1. 完全關閉 Claude Desktop
   2. 重新開啟 Claude Desktop
   3. 在 MCP 工具清單中尋找 'aidefend'（Search and tools 圖示 ⚙️）

======================================================================
  ✅ 安裝完成！
======================================================================

下一步：
  1. 重新啟動 Claude Desktop（完全關閉後再開啟）
  2. 在 MCP 工具中尋找 'aidefend'（Search and tools 圖示 ⚙️）
  3. 試試：「搜尋 AIDEFEND 中關於 prompt injection 的防禦手法」
```

### 步驟 4：重啟 Claude Desktop

**重要：** 你必須**完全退出** Claude Desktop（不只是關閉視窗），然後重新開啟。

**Windows：**
- 工作列右鍵點擊 Claude 圖示 → Exit

**macOS：**
- 按 `Cmd+Q`（或 Claude 選單 → 結束）

**驗證工具已載入：**
- 開啟 Claude Desktop
- 工具應該會出現在可用工具面板中
- 問 Claude：「有哪些 AIDEFEND 工具可用？」

### 步驟 5：首次使用 - 模型下載

⚠️ **重要：** **首次使用**時，AIDEFEND 會自動下載約 1.1GB 的 embedding 模型（`multilingual-e5-base`）。

**預期情況：**
- **下載時間：** 4-8 分鐘（取決於網路速度）
- **儲存空間：** 總共約 3-4GB（模型 + 相依套件 + 知識庫 - 詳細分解請見上方系統需求）
- **存放位置：** `~/.cache/fastembed/`（macOS/Linux）或 `%USERPROFILE%\.cache\fastembed\`（Windows）
- **僅此一次：** 後續使用會立即回應

**如果 Claude 第一次查詢時很慢：**
- 正在背景下載模型
- 如有需要可檢查 MCP 伺服器日誌
- 等待幾分鐘後再試

**離線使用：**
- 首次下載後，AIDEFEND 可完全離線運作
- 不會對外發送任何 API 請求
- 所有處理皆為 100% 本地運算

### 替代方案：安裝選項

安裝腳本支援多種模式：

```bash
# 僅檢查前置需求（不安裝）
python scripts/install.py --check

# 互動模式（預設）- 會詢問確認
python scripts/install.py

# 自動模式 - 不詢問確認
python scripts/install.py --auto

# 跳過 MCP 設定 - 僅安裝依賴
python scripts/install.py --no-mcp

# 試運行 - 預覽但不進行變更
python scripts/install.py --dry-run

# 顯示說明
python scripts/install.py --help
```

**建議工作流程：**
```bash
# 1. 先檢查前置需求
python scripts/install.py --check

# 2. 若一切正常，執行安裝
python scripts/install.py
```

### 反安裝 MCP 模式

若要從 Claude Desktop 移除 AIDEFEND（但保留專案檔案）：

```bash
python scripts/uninstall_mcp.py
```

這會：
- ✅ 從 Claude 設定檔移除 AIDEFEND
- ✅ 保留所有其他 MCP 工具
- ✅ 移除前建立備份
- ✅ 保留你的本地專案檔案

---

## 🔌 Claude Code 設定（VSCode 擴充）

**適用於：想要在 Claude Code (VSCode 擴充) 中使用 AIDEFEND 的使用者**

Claude Code 使用不同於 Claude Desktop 的設定格式（`.mcp.json`）。

### 快速設定

```bash
# 只安裝給 Claude Code
python scripts/install.py --client code

# 或同時安裝給 Claude Desktop 和 Claude Code
python scripts/install.py --client both
```

**這個指令會：**
- ✅ 安裝所有依賴（與 Claude Desktop 相同）
- ✅ 在專案根目錄建立 `.mcp.json`
- ✅ **安全合併**現有的 `.mcp.json`（保留其他 servers）
- ✅ 可以 commit 到 git（與團隊分享）

### 安裝後步驟

1. **重新載入 VSCode 視窗**：
   - 按 `Ctrl+Shift+P`（Windows/Linux）或 `Cmd+Shift+P`（macOS）
   - 輸入 "Reload Window" 並按 Enter

2. **驗證 AIDEFEND 可用**：
   - 在 MCP 工具面板中尋找 `aidefend`
   - 嘗試透過 `/` 斜線命令使用 AIDEFEND 工具

### Claude Code vs Claude Desktop

| 項目 | Claude Desktop | Claude Code |
|------|----------------|-------------|
| **設定檔** | `claude_desktop_config.json` | `.mcp.json`（專案根目錄） |
| **位置** | 使用者設定目錄 | 專案目錄 |
| **版本控制** | 不分享 | 可 commit 到 git |
| **團隊分享** | 每位使用者手動設定 | 自動（透過 git） |
| **客戶端存取** | 僅限桌面應用程式 | 僅限 VSCode |

### .mcp.json 範例

```json
{
  "mcpServers": {
    "aidefend": {
  "mcpServers": {
    "aidefend": {
      "command": "C:/path/to/python.exe",
      "args": [
        "C:/Users/you/aidefend-mcp/__main__.py",
        "--mcp"
      ],
      "env": {}
    }
  }
}
```

> **注意：** 安裝腳本會自動偵測您的實際 Python 路徑並正確填入。上方的範例僅使用佔位符。

---

### 安裝問題疑難排解

#### Python/Node.js 版本錯誤

**問題：** `python --version` 顯示 Python 2.x 或找不到命令

**macOS/Linux 解決方案：**
```bash
# 改用 python3
python3 --version
python3 scripts/install.py
```

**Windows 解決方案：**
```bash
# 從 https://www.python.org/downloads/ 安裝 Python 3.9+
# 安裝時確保勾選「Add Python to PATH」
```

#### `pip install` 失敗或逾時

**問題：** 網路問題、防火牆或下載緩慢

**解決方案 1 - 檢查網路：**
```bash
python scripts/install.py --check  # 驗證連線
```

**解決方案 2 - 中國大陸使用者：**
```bash
# 使用清華鏡像源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
npm install --registry=https://registry.npmmirror.com
```

**解決方案 3 - 企業代理：**
```bash
pip install -r requirements.txt --proxy YOUR_PROXY_URL
```

**解決方案 4 - 升級 pip：**
```bash
python -m pip install --upgrade pip
```

#### `npm install` 失敗

**問題：** npm 錯誤或權限問題

**解決方案 1 - 清除快取：**
```bash
npm cache clean --force
npm install
```

**解決方案 2 - 使用不同 registry：**
```bash
npm install --registry=https://registry.npmjs.org/
```

#### 未偵測到 Claude Desktop

**問題：** 警告找不到 Claude Desktop

**解決方案：**
- 從 https://claude.ai/download 安裝 Claude Desktop
- 設定檔仍會被建立，等你安裝後即可使用
- 如果只想用 REST API 模式則不需要

#### 依賴與其他專案衝突

**問題：** 「版本衝突」或「無法安裝 pydantic 2.x」

**解決方案 - 使用虛擬環境：**
```bash
# 建立隔離環境
python -m venv venv
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows

# 然後安裝
python scripts/install.py
```

#### 第一次查詢非常慢

**問題：** Claude 在第一次 AIDEFEND 查詢時卡住 2-5 分鐘

**原因：** 正在下載約 400MB 的 embedding 模型（僅此一次）

**解決方案：**
- 等待模型下載完成（檢查網路連線）
- 後續查詢會立即回應
- 模型儲存位置：`~/.cache/fastembed/`（macOS/Linux）或 `%USERPROFILE%\.cache\fastembed\`（Windows）

#### MCP 工具未顯示在 Claude Desktop

**問題：** 重啟後看不到 AIDEFEND

**檢查清單：**
1. 是否完全退出 Claude Desktop？（不只是關閉視窗）
   - Windows：工作列右鍵 → Exit
   - macOS：Cmd+Q
2. 檢查設定檔是否存在：
   - Windows：`%APPDATA%\Claude\claude_desktop_config.json`
   - macOS：`~/Library/Application Support/Claude/claude_desktop_config.json`
3. 檢查設定檔格式是否為有效 JSON（無尾隨逗號）
4. 再次重啟 Claude Desktop
5. 檢查 Claude Desktop 日誌是否有錯誤

#### 仍有問題？

```bash
# 執行診斷檢查
python scripts/install.py --check

# 查看詳細日誌
cat data/logs/aidefend_mcp.log  # macOS/Linux
type data\logs\aidefend_mcp.log  # Windows
```

如需更多協助，請參閱下方完整疑難排解指南或在 GitHub 開啟 issue。

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
# 你應該會看到 README.md、scripts/、app/ 等檔案
ls  # macOS/Linux
dir # Windows
```

---

### 步驟 2: 啟動服務

**在任何平台上（Windows/macOS/Linux）：**
```bash
python __main__.py
```

**首次執行時會自動：**
1. ✅ 從 GitHub 自動同步 AIDEFEND framework（5-15 分鐘）
2. ✅ 解析並索引所有安全技術
3. ✅ 在 http://localhost:8000 啟動 REST API 伺服器
4. ✅ 服務準備就緒，可以開始查詢

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

> **🔒 安全提示：** 對於生產環境部署，我們強烈建議在 `.env` 中啟用 API Key 驗證：
> ```bash
> AUTH_MODE=api_key
> AIDEFEND_API_KEY=<your-secure-random-key>
> ```

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
Collecting fastapi==0.121.1
Downloading fastapi-0.121.1-py3-none-any.whl (92 kB)
...
Installing collected packages: ...
Successfully installed fastapi-0.121.1 ...
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
# 預設（REST API 模式）
C:/Python313/python.exe __main__.py

# 或明確指定 REST API 模式
C:/Python313/python.exe __main__.py --api
```

**這個指令的意思：**
- 執行 AIDEFEND 服務的主程式
- 預設會啟動 REST API 模式（或使用 `--api` flag 明確指定）
- 服務會在 `127.0.0.1:8000` 執行
- 所有設定從 `.env` 檔案載入
- 使用 `--mcp` flag 啟動 MCP 模式，`--resync` 重建資料庫，`--help` 顯示說明

**預期輸出：**
```
Starting AIDEFEND REST API Server...
API will be available at: http://127.0.0.1:8000
API documentation: http://127.0.0.1:8000/docs
------------------------------------------------------------
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
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
在大部分的 Windows 11 機器上，這個位置可能在: C:\Users\\[您的使用者名稱]\AppData\Roaming\Claude\

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
      "command": "C:/Python313/python.exe",
      "args": [
        "/REPLACE/WITH/ABSOLUTE/PATH/TO/aidefend-mcp/__main__.py",
        "--mcp"
      ],
      "cwd": "/REPLACE/WITH/ABSOLUTE/PATH/TO/aidefend-mcp"
    }
  }
}
```

**⚠️ 重要：** 將所有路徑替換為您實際的絕對路徑！

1. **Python 執行檔路徑**（在 `command` 欄位中）：
   - 將 `C:/Python313/python.exe` 替換為您實際的 Python 安裝路徑
   - 如何找到您的 Python 路徑：
     - **Windows：** 在命令提示字元執行 `where python`
     - **macOS/Linux：** 在終端機執行 `which python` 或 `which python3`
   - 常見位置：
     - Windows：`C:/Python313/python.exe`、`C:/Python312/python.exe`、`C:/Users/YourName/AppData/Local/Programs/Python/Python313/python.exe`
     - macOS：`/usr/local/bin/python3`、`/opt/homebrew/bin/python3`
     - Linux：`/usr/bin/python3`、`/usr/local/bin/python3`

2. **專案路徑**（在 `args` 和 `cwd` 欄位中）：
   - 將 `args` 中的路徑替換為 `__main__.py` 檔案的**完整絕對路徑**
   - 將 `cwd` 替換為專案**根目錄**的絕對路徑
   - `cwd` 欄位是必要的，讓 Python 能正確載入專案內的相對模組

**如何找到你的路徑：**

**macOS/Linux:**
```bash
cd /path/to/aidefend-mcp
echo "args: [\"$(pwd)/__main__.py\", \"--mcp\"]"
echo "cwd: \"$(pwd)\""
```
複製輸出結果使用。

**Windows:**
```powershell
cd C:\path\to\aidefend-mcp
$path = (Get-Location).Path -replace '\\', '/'
Write-Host "args: [`"$path/__main__.py`", `"--mcp`"]"
Write-Host "cwd: `"$path`""
```
這會輸出已轉換為正斜線的完整路徑。

**重要提示：**
- ✅ 正確：在 JSON 中使用**正斜線** `/`
  - `"args": ["C:/Users/YourName/projects/aidefend-mcp/__main__.py", "--mcp"]`
  - `"cwd": "C:/Users/YourName/projects/aidefend-mcp"`
- ❌ 錯誤：在 JSON 中使用反斜線 `\`（會導致解析錯誤）

---

### 步驟 3：設定範例

**範例 1：macOS 安裝**
```json
{
  "mcpServers": {
    "aidefend": {
      "command": "C:/Python313/python.exe",
      "args": ["/Users/alice/projects/aidefend-mcp/__main__.py", "--mcp"],
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
      "command": "C:/Python313/python.exe",
      "args": ["C:/Users/Bob/Documents/aidefend-mcp/__main__.py", "--mcp"],
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
      "command": "C:/Python313/python.exe",
      "args": ["/Users/alice/projects/aidefend-mcp/__main__.py", "--mcp"],
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
   C:/Python313/python.exe __main__.py --mcp
   ```

   你應該會看到：`Starting AIDEFEND MCP Server (stdio mode)...`

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
C:/Python313/python.exe __main__.py  # 以 API 模式啟動
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
C:/Python313/python.exe __main__.py          # REST API 在 http://localhost:8000
```

終端機 2：
```bash
# 如上所示設定 Claude Desktop 的 MCP 模式
# 當 Claude Desktop 連線時，MCP 會自動執行
```

兩種模式共享相同的知識庫和同步服務 - 它們會自動保持同步。

---

## 疑難排解常見問題

### ℹ️ 關於自動快取管理

**好消息：你永遠不需要手動刪除快取檔案！**

AIDEFEND MCP 使用**自動快取失效機制**確保資料一致性：

**自動更新：**
- ✅ **內容更新**：系統每小時檢查 GitHub 是否有新技術，自動更新
- ✅ **Schema 更新**：當 metadata 格式改變時，快取自動失效
- ✅ **模型變更**：自動檢測並觸發重建

**何時需要使用 `--resync`：**
只在特殊情況需要：
- 更換 embedding 模型（例如從 e5-base 改成 embeddinggemma）
- 資料庫損壞
- 開發/測試需要乾淨狀態

**自動更新時會發生什麼：**
```
系統偵測變更 → 下載新資料 → 更新 embeddings → 可以使用
```
不需要使用者介入！

---

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

**對於 data 目錄：**
```bash
chmod -R 755 data/
```

**對於主程式：**
```bash
chmod +x __main__.py
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

## 疑難排解

### 重新同步資料庫

如果遇到資料庫問題或需要升級 embedding 模型，請使用 resync 指令：

```bash
python __main__.py --resync
```

**何時使用：**
- ✅ 升級到不同的 embedding 模型
- ✅ 資料庫損壞或錯誤
- ✅ 想要從乾淨狀態開始
- ✅ 在 `.env` 中變更 `EMBEDDING_MODEL` 後

**執行內容：**
1. 刪除現有資料庫（`data/aidefend_kb.lancedb`）
2. 刪除版本追蹤（`data/local_version.json`）
3. 從 GitHub 重新下載內容
4. 使用目前設定重建資料庫
5. 重新建立 embedding 快取

**注意：** 這是安全操作 - 所有資料都可以從來源儲存庫恢復。

**重新同步後，啟動您偏好的模式：**
```bash
# 啟動 MCP 模式
python __main__.py --mcp

# 或啟動 REST API
python __main__.py --api
```

### 常見問題

**資料庫模型不匹配：**
```
❌ Embedding model upgrade detected!
   Database model: intfloat/multilingual-e5-small (384d)
   Configured model: Xenova/multilingual-e5-base (768d)
```
**解決方案：** 執行 `python __main__.py --resync`

**資料庫損壞：**
```
Error: Failed to load database
```
**解決方案：** 執行 `python __main__.py --resync`

**服務沒有回應：**
- 檢查服務是否正在執行：`ps aux | grep python`（Unix）或工作管理員（Windows）
- 檢查日誌：`tail -f data/logs/aidefend_mcp.log`
- 重新啟動服務

**MCP 工具未顯示在 Claude Desktop：**
- 驗證 `claude_desktop_config.json` 路徑為絕對路徑（非相對路徑）
- 完全重新啟動 Claude Desktop
- 檢查 Python 路徑：`which python3`（Unix）或 `where python`（Windows）

---

**有問題？Issues？功能請求？**

開啟 issue：https://github.com/edward-playground/aidefend-mcp/issues

**祝你部署順利！🚀**
