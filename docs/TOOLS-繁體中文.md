# AIDEFEND MCP 工具 - 完整參考文件

本文件提供 AIDEFEND MCP Service 中所有 **18 個 MCP 工具**的詳細文件。

> **即時資料說明：** 本文件中的 ID、名稱與語料筆數已對齊 AIDEFEND
> 1.20260805（public schema 2.3、MCP index schema 3.3：92 個 techniques +
> 265 個 sub-techniques + 851 筆 guidance =
> 1,208 份文件）。排名、分數、時間、framework coverage 總數與工具數量
> 都會依客戶實際同步的版本重新計算；這些快照筆數只是範例，不是 runtime
> 驗收門檻。服務會動態處理內容、ID、標題、筆數、順序與相容的新增欄位，
> 包含開源、source-available/open-weight 與商業工具。daily upstream canary
> 會驗證持續更新的公開來源；無效或確實不相容的候選資料不會啟用，既有安裝
> 會繼續使用 last-known-good index。任意破壞性 schema 仍需要服務版本明確
> 支援。要引用為即時結果前，請先呼叫 get_aidefend_status 與
> validate_technique_id。

## 工具分類

### 基礎查詢工具（3 個工具）
與 AIDEFEND 知識庫互動的必備工具。

### 專業分析工具（15 個工具）
為 AI 安全從業人員、資安工程師和開發人員設計的專業 P0 工具。

---

## 基礎查詢工具

### 工具 1：查詢 AIDEFEND

**用途**：使用自然語言查詢搜尋 AIDEFEND AI 安全防禦知識庫。

**何時使用**：尋找 AI/ML 安全威脅的防禦策略、技術和最佳實踐。

#### MCP 模式範例（Claude Desktop）：

```
你：「如何防禦 prompt injection 攻擊？」

Claude：[使用 query_aidefend 工具]
        根據 AIDEFEND，以下是主要的防禦技術：

        1. AID-H-001：Adversarial Robustness Training
        2. AID-H-002：AI-Contextualized Data Sanitization & Input Validation
        3. AID-D-001：Adversarial Input, Prompt Injection & Signal-Authenticity Detection
        ...
```

#### REST API 範例：

```bash
curl -X POST "http://localhost:8000/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query_text": "如何防止 prompt injection",
    "top_k": 5
  }'
```

---

### 工具 2：取得 AIDEFEND 狀態

**用途**：檢查 AIDEFEND 知識庫的目前狀態，包含 framework 版本、已索引的文件總數、embedding 模型資訊和同步狀態。

**何時使用**：驗證服務就緒狀態、檢查 framework 版本、檢查同步狀態、疑難排解。

#### MCP 模式範例（Claude Desktop）：

```
你：「AIDEFEND 服務的狀態如何？」

Claude：[使用 get_aidefend_status 工具]
        AIDEFEND 知識庫狀態：
        - Framework Version：1.20260805
        - Framework Source Revision：e10c1678
        - Framework Public Schema：2.3
        - MCP Index Schema：3.3
        - Framework Migration Registry Schema：1.0
        - 已索引文件：1,208
        - 服務就緒：是
```

#### REST API 範例：

```bash
curl http://localhost:8000/api/v1/status
```

**節錄回應欄位：**
```json
{
  "status": "online",
  "sync_info": {
    "framework_version": "1.20260805",
    "source_revision": "e10c1678ee49f03f8fb0c97d446ba3fbc3543655",
    "framework_public_schema_version": "2.3",
    "index_schema_version": "3.3",
    "framework_migrations_schema_version": "1.0",
    "framework_migrations_registry_version": "2026-08-05",
    "total_documents": 1208,
    "is_syncing": false
  }
}
```

Framework Public Schema metadata 會從與已索引 tactics 相同的
Framework source revision 中讀取 `data/data.json`。

---

### 工具 3：同步 AIDEFEND

**用途**：手動觸發與 AIDEFEND GitHub repository 的同步，以取得最新的防禦戰術和技術。

**何時使用**：強制更新至最新 framework 版本、疑難排解過時內容。

**注意**：自動同步預設每小時執行一次。此操作可能需要幾分鐘。

#### MCP 模式範例（Claude Desktop）：

```
你：「可以同步 AIDEFEND 知識庫至最新版本嗎？」

Claude：[使用 sync_aidefend 工具]
        開始與 GitHub 同步...
        下載最新內容...
        解析技術...
        生成 embeddings...
        ✅ 同步完成！知識庫已更新至版本 1.20260805
```

#### REST API 範例：

```bash
curl -X POST "http://localhost:8000/api/v1/sync"
```

**回應：**
```json
{
  "status": "success",
  "message": "Sync completed successfully",
  "framework_version": "1.20260805",
  "documents_synced": 1208,
  "sync_duration_seconds": 42.3
}
```

---

## 專業分析工具（P0 工具）

### 工具 4：取得統計資訊

**用途**：取得 AIDEFEND 知識庫的完整總覽 - 文件總數、依 tactic/pillar/phase 的涵蓋範圍，以及威脅 framework 涵蓋範圍。

**何時使用**：了解知識庫範圍、生成報告、或檢查資料完整性。

#### MCP 模式範例（Claude Desktop）：

```
你：「可以顯示 AIDEFEND 知識庫的統計資訊嗎？」

Claude：[使用 get_statistics 工具]
        AIDEFEND 知識庫包含：
        - 1,208 份文件總數（92 個 techniques、265 個 sub-techniques、851 個 strategies）
        - 涵蓋 7 個 tactics：Model、Harden、Detect、Isolate、Deceive、Evict、Restore
        - 威脅 framework 涵蓋範圍：10 個 OWASP LLM Top 10 2026 風險、28 個 MITRE ATLAS 技術
        - 299 個 controls 有開源工具、34 個有 source-available/open-weight 工具、
          275 個有商業工具
        - 42 份文件包含程式碼片段
```

#### REST API 範例：

```bash
curl http://localhost:8000/api/v1/statistics
```

**回應：**
```json
{
  "overview": {
    "total_documents": 1208,
    "total_techniques": 92,
    "total_subtechniques": 265,
    "total_strategies": 851,
    "total_actionable_items": 300
  },
  "by_tactic": {
    "Harden": 18,
    "Detect": 12,
    "Isolate": 8,
    "Model": 7
  },
  "threat_framework_coverage": {
    "owasp_llm_items_covered": 10,
    "owasp_llm_total_items": 10,
    "owasp_llm_coverage_percentage": 100.0,
    "mitre_atlas_items_covered": 28,
    "maestro_items_covered": 15,
    "techniques_with_threat_mappings": 40,
    "techniques_mapped_percentage": 88.9
  },
  "tools_availability": {
    "techniques_with_opensource_tools": 299,
    "techniques_with_source_available_tools": 34,
    "techniques_with_commercial_tools": 275
  },
  "code_snippets": {
    "documents_with_code_snippets": 42
  }
}
```

---

### 工具 5：驗證技術 ID

**用途**：驗證技術 ID 是否存在且格式正確。如果找不到 ID，提供模糊比對建議。

**何時使用**：查詢特定技術前、檢查文件中的 ID 是否有效、或尋找相似技術。

#### MCP 模式範例（Claude Desktop）：

```
你：「AID-H-001 是有效的技術 ID 嗎？」

Claude：[使用 validate_technique_id 工具]
        是的，AID-H-001 是有效的！
        - 名稱：Adversarial Robustness Training
        - 類型：technique
        - Tactic：Harden
```

```
你：「那 AID-H-999 呢？」

Claude：[使用 validate_technique_id 工具]
        在知識庫中找不到 AID-H-999。
        您是否要找：
        - AID-H-001（Adversarial Robustness Training）- 85% 符合
        - AID-H-002（AI-Contextualized Data Sanitization & Input Validation）- 78% 符合
```

#### REST API 範例：

```bash
# 有效的 ID
curl -X POST "http://localhost:8000/api/v1/validate-technique-id?technique_id=AID-H-001"
```

**回應：**
```json
{
  "valid": true,
  "technique": {
    "id": "AID-H-001",
    "name": "Adversarial Robustness Training",
    "type": "technique",
    "tactic": "Harden"
  }
}
```

```bash
# 無效的 ID 與建議
curl -X POST "http://localhost:8000/api/v1/validate-technique-id?technique_id=AID-H-999"
```

**回應：**
```json
{
  "valid": false,
  "reason": "NOT_FOUND",
  "suggestions": [
    {
      "id": "AID-H-001",
      "name": "Adversarial Robustness Training",
      "similarity_score": 0.85
    }
  ]
}
```

---

### 工具 6：取得技術詳情

**用途**：取得特定技術的完整詳情，包含所有 sub-techniques、實作策略（含程式碼範例）、工具建議和威脅對應。

**何時使用**：深入了解特定防禦技術、實作防禦控制、或理解技術防禦哪些威脅。

#### MCP 模式範例（Claude Desktop）：

```
你：「顯示技術 AID-H-002 的所有詳情」

Claude：[使用 get_technique_detail 工具]
        以下是 AID-H-002
        （AI-Contextualized Data Sanitization & Input Validation）的完整分解：

        主要技術：
        - Tactic：Harden
        - 完整列出 parent 與每個 child 的威脅對應

        Sub-Techniques（8 個）：
        1. AID-H-002.001：Training & Fine-Tuning Data Sanitization
           - 4 筆 implementation guidance
        2. AID-H-002.002：Inference-Time Prompt & Input Validation
           - 8 筆 implementation guidance
        3. AID-H-002.003：Multimodal Input Sanitization
           - 4 筆 implementation guidance
        ...另有 5 個 sub-techniques，完整回傳、不截斷

        可用工具：
        - 開源、source-available 與商業工具皆依已同步 framework 完整回傳，
          不在文件中固定列出 vendor
```

#### REST API 範例：

```bash
curl "http://localhost:8000/api/v1/technique/AID-H-002?include_code=true&include_tools=true"
```

**回應**（縮寫）：
```json
{
  "technique": {
    "id": "AID-H-002",
    "name": "AI-Contextualized Data Sanitization & Input Validation",
    "type": "technique",
    "tactic": "Harden",
    "description": "AI-contextualized data sanitization and input validation...",
    "tools": {
      "opensource": [],
      "source_available": [],
      "commercial": []
    }
  },
  "subtechniques": [
    {
      "id": "AID-H-002.002",
      "name": "Inference-Time Prompt & Input Validation",
      "strategies": [
        {
          "strategy": "Pydantic-based validation",
          "how_to": "Use Pydantic models to validate input schema...",
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
    "total_subtechniques": 8,
    "total_strategies": 32
  }
}
```

#### ⚡ 效能提示

若您需要**同時取得多個技術**的實作策略（例如實作計畫中的前 5-10 個建議），請改用**工具 13：取得實作計畫**並設定 `detail_level="standard"` 或 `"detailed"`。這可避免為每個建議分別發送詳細請求；實際延遲取決於主機、模型快取與請求結果數量。

**範例情境：**
- 較多往返：取得實作計畫（基本）→ 針對每個建議呼叫 `get_technique_detail`
- 較少往返：取得實作計畫並設定 `detail_level="standard"`

在以下情況使用 get_technique_detail：
- 需要前幾名建議**以外**的**單一技術**詳情
- 需要排名前 5 名以外的技術完整資訊
- 直接查詢技術 ID

---

### 工具 7：取得威脅防禦

**用途**：針對特定威脅尋找 AIDEFEND 防禦技術。支援 OWASP LLM Top 10 2026 ID 與已宣告的舊 edition alias、MITRE ATLAS、MAESTRO，或自然語言關鍵字。成功同步現行框架後，OWASP LLM 查詢一律回傳目前 2026 語料的防禦結果。

**何時使用**：威脅導向的防禦規劃、回應特定漏洞、或建立防禦路線圖。

#### MCP 模式範例（Claude Desktop）：

```
你：「2025 年 OWASP LLM03 Supply Chain 在現行版本有哪些防禦？」

Claude：[使用 get_defenses_for_threat 工具]
        查詢：LLM03:2025
        解析狀態：migrated
        現行 canonical 風險：LLM04:2026 Supply Chain
        原始項目：LLM03:2025 Supply Chain

        回傳的是經過審查、實際對應至現行 LLM04:2026 Supply Chain
        定義的控制；服務不會重播 2025 mapping，也不會自動沿用舊 mapping。
```

**OWASP LLM edition 解析規則**：

- 裸 rank 或 `:latest` 一律代表現行 edition。例如，`LLM03` 與 `LLM03:latest` 會解析為 `LLM03:2026 Excessive Agency`，不會被當成 2025 年的 Supply Chain。
- 明確指定已被取代的 ID 時，會依宣告的語意後繼項目解析。因此，`LLM03:2025 Supply Chain` 會解析為 `LLM04:2026 Supply Chain`，並以 `LLM04` 作為 reverse-index lookup key。
- `LLM03:2025x` 這類格式錯誤或不支援的參照會回傳 `resolution.status="invalid"`。若同一查詢包含不同概念，例如 `LLM03:2025 / LLM06:2025`，則回傳 `resolution.status="ambiguous"` 與現行候選項目。
- 只有 ID、且解析結果為 invalid 或 ambiguous 的查詢，會以 `search_method="resolution_only"` 回傳零筆結果；服務不會猜測 rank，也不會掃描防禦索引。使用者須改為提交一個可辨識的風險概念。

```
你：「如何防禦模型投毒攻擊？」

Claude：[使用 get_defenses_for_threat 工具，使用關鍵字搜尋]
        針對「模型投毒」，以下是相關防禦：

        1. AID-M-001：AI Asset Inventory & Mapping（語意符合度：0.89）
        2. AID-D-003：AI Output Monitoring & Policy-Violation Detection（語意符合度：0.85）
        3. AID-H-004：Identity, Access & Trusted Communication for AI Systems（語意符合度：0.82）
```

#### REST API 範例：

```bash
# 將已被取代的 OWASP LLM 概念解析至現行語料
curl -X POST "http://localhost:8000/api/v1/defenses-for-threat?threat_id=LLM03%3A2025&top_k=5"
```

**回應 metadata 節錄**（此處省略防禦清單）：
```json
{
  "threat_query": {
    "threat_id": "LLM03:2025",
    "threat_keyword": null,
    "normalized_threat_id": "LLM04",
    "lookup_threat_id": "LLM04",
    "canonical_threat_id": "LLM04:2026",
    "resolution": {
      "status": "migrated",
      "input": "LLM03:2025",
      "canonical": {
        "frameworkKey": "owasp_llm",
        "framework": "OWASP LLM Top 10 2026",
        "edition": "2026",
        "id": "LLM04:2026",
        "name": "Supply Chain",
        "label": "LLM04:2026 Supply Chain"
      },
      "reason": "The risk moved from rank 3 to rank 4 and now explicitly treats promoted artifacts, adapters, conversion, merge, quantization, and on-device delivery as first-class supply-chain surfaces.",
      "migratedFrom": {
        "edition": "2025",
        "id": "LLM03:2025",
        "name": "Supply Chain",
        "label": "LLM03:2025 Supply Chain"
      }
    }
  },
  "search_method": "exact"
}
```

```bash
# 依關鍵字搜尋
curl -X POST "http://localhost:8000/api/v1/defenses-for-threat?threat_keyword=prompt%20injection&top_k=10"
```

---

### 工具 8：取得安全程式碼片段

**用途**：從 AIDEFEND 實作策略中提取可執行的安全程式碼片段。依技術 ID 或主題關鍵字搜尋，取得可直接複製貼上的程式碼範例。

**何時使用**：實作特定安全控制、尋找程式碼範例、或快速原型開發。

#### MCP 模式範例（Claude Desktop）：

```
你：「顯示輸入驗證的程式碼範例」

Claude：[使用 get_secure_code_snippet 工具]
        我找到了 5 個輸入驗證的程式碼片段：

        片段 1（Python）：
        from pydantic import BaseModel, Field

        class UserPrompt(BaseModel):
            text: str = Field(max_length=500)

        def validate_input(prompt: str):
            return UserPrompt(text=prompt)

        片段 2（JavaScript）：
        const Joi = require('joi');
        const schema = Joi.string().max(500).required();
        ...
```

#### REST API 範例：

```bash
# 取得特定技術的程式碼
curl -X POST "http://localhost:8000/api/v1/code-snippets?technique_id=AID-H-002.002&max_snippets=5"
```

**回應：**
```json
{
  "query": {
    "technique_id": "AID-H-002.002",
    "topic": null,
    "language_filter": null
  },
  "code_snippets": [
    {
      "technique_id": "AID-H-002.002",
      "technique_name": "Inference-Time Prompt & Input Validation",
      "tactic": "Harden",
      "code": "from pydantic import BaseModel, Field\n\nclass UserPrompt(BaseModel):\n    text: str = Field(max_length=500)",
      "language": "python",
      "description": "Use Pydantic for input validation",
      "usage_context": "Validate user prompts before sending to LLM"
    }
  ],
  "total_snippets": 5,
  "usage_notes": {
    "security_warning": "Review and test all code before using in production",
    "adaptation_required": "Code snippets may need adaptation to your specific environment"
  }
}
```

```bash
# 依主題搜尋並篩選語言
curl -X POST "http://localhost:8000/api/v1/code-snippets?topic=RAG%20security&language=python&max_snippets=3"
```

#### 💡 最佳實踐工作流程

處理實作計畫時，使用以下推薦工作流程：

1. **取得概覽**：使用**工具 13：取得實作計畫**並設定 `detail_level="standard"` 以取得技術建議與簡短策略摘要
2. **呈現給使用者**：展示建議與摘要，協助使用者選擇優先項目
3. **取得程式碼範例**：針對使用者想要實作的特定技術使用 `get_secure_code_snippet`

**範例情境：**
- 較多往返：取得計畫（基本）→ 針對每個建議呼叫 `get_technique_detail` → 針對每個建議呼叫 `get_secure_code_snippet`
- 較少往返：取得計畫（標準）→ 展示摘要 → 僅針對選定技術呼叫 `get_secure_code_snippet`

在以下情況使用 get_secure_code_snippet：
- 需要前幾名建議**以外**的**特定技術**程式碼
- 需要完整程式碼集合並使用**語言篩選**

---

### 工具 9：分析涵蓋範圍

**用途**：根據已實作的技術分析防禦涵蓋範圍並找出缺口。提供依 tactic/pillar/phase 的涵蓋百分比、威脅 framework 涵蓋範圍，以及優先順序建議。

**何時使用**：安全方案管理、缺口分析、優先化安全投資、或向領導層報告。

#### MCP 模式範例（Claude Desktop）：

```
你：「我已實作 AID-H-001、AID-H-002 和 AID-D-001。我的涵蓋範圍如何？」

Claude：[使用 analyze_coverage 工具]
        您的防禦涵蓋範圍分析：

        整體涵蓋範圍：1.0%（已實作 300 個可執行控制中的 3 個）
        涵蓋等級：最低

        依 Tactic 的涵蓋範圍：
        - Harden：11%（18 個技術中的 2 個）
        - Detect：8%（12 個技術中的 1 個）
        - Isolate：0% ⚠️ 重大缺口
        - Model：0% ⚠️ 重大缺口

        重大缺口：
        1. 無 Isolate 技術 - 完全缺乏隔離能力
        2. 無 Model 技術 - 無模型強化防禦

        建議後續步驟：
        1. 實作 AID-I-001（AI Execution Sandboxing & Runtime Isolation）- 高優先順序
        2. 實作 AID-M-001（AI Asset Inventory & Mapping）- 高優先順序
        3. 在 Harden tactic 達成 50%+ 涵蓋率
```

#### REST API 範例：

```bash
curl -X POST "http://localhost:8000/api/v1/analyze-coverage" \
  -H "Content-Type: application/json" \
  -d '{
    "implemented_techniques": ["AID-H-001", "AID-H-002", "AID-D-001"],
    "system_type": "rag"
  }'
```

**回應：**
```json
{
  "analysis_summary": {
    "total_techniques_available": 300,
    "techniques_implemented": 3,
    "coverage_percentage": 1.0,
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
      "reason": "No Isolate techniques implemented",
      "risk": "Complete lack of Isolate capability"
    }
  ],
  "recommendations": [
    {
      "rank": 1,
      "technique_id": "AID-I-001",
      "name": "AI Execution Sandboxing & Runtime Isolation",
      "tactic": "Isolate",
      "priority": "HIGH",
      "reason": "Fills Isolate tactic gap",
      "impact": "High - Establishes defensive capability"
    }
  ],
  "next_steps": {
    "immediate": [
      "Implement AID-I-001 (AI Execution Sandboxing & Runtime Isolation) - Fills Isolate tactic gap"
    ],
    "short_term": [
      "Achieve 50%+ coverage in all tactics",
      "涵蓋 OWASP LLM Top 10 2026 中優先度最高的 5 個風險"
    ],
    "long_term": [
      "Achieve 80%+ overall coverage",
      "Implement defense-in-depth across all pillars"
    ]
  }
}
```

---

### 工具 10：對應至合規 Framework

**用途**：使用啟發式分析將 AIDEFEND 技術對應至合規 framework 要求（NIST AI RMF、EU AI Act、ISO 42001、CSA AI Controls、OWASP ASVS）。

**100% 本地處理** - 使用基於 tactic 對齊的本地啟發式比對，無外部 API 呼叫。

**何時使用**：合規報告、稽核準備、治理文件、或展示法規遵循。

#### MCP 模式範例（Claude Desktop）：

```
你：「將 AID-H-001 和 AID-D-001 對應至 NIST AI RMF」

Claude：[使用 map_to_compliance_framework 工具]
        對應至 NIST AI RMF 的合規對應：

        AID-H-001（Adversarial Robustness Training）：
        - 對應至：GOVERN-1.2、MANAGE-2.1
        - 信心度：中
        - 理由：輸入驗證與風險管理和治理控制相符

        AID-D-001（Adversarial Input, Prompt Injection & Signal-Authenticity Detection）：
        - 對應至：MEASURE-2.1、MANAGE-4.1
        - 信心度：中
        - 理由：偵測技術與量測和事故管理相符

        ⚠️ 注意：對應結果應由合規專家審查
```

#### REST API 範例：

```bash
curl -X POST "http://localhost:8000/api/v1/compliance-mapping" \
  -H "Content-Type: application/json" \
  -d '{
    "technique_ids": ["AID-H-001", "AID-D-001"],
    "framework": "nist_ai_rmf"
  }'
```

**回應：**
```json
{
  "framework": {
    "id": "nist_ai_rmf",
    "name": "NIST AI Risk Management Framework"
  },
  "mappings": [
    {
      "technique_id": "AID-H-001",
      "technique_name": "Adversarial Robustness Training",
      "technique_tactic": "Harden",
      "framework": "nist_ai_rmf",
      "framework_name": "NIST AI Risk Management Framework",
      "framework_controls": ["GOVERN-1.2", "MANAGE-2.1"],
      "mapping_confidence": "medium",
      "mapping_rationale": "基於 tactic 'Harden' 與 framework 要求的對齊進行對應",
      "additional_considerations": [
        "與合規團隊審查以確保完整性",
        "依特定使用案例可能需要額外控制",
        "考慮與其他技術組合以達成完整合規"
      ]
    }
  ],
  "total_mapped": 2,
  "mapping_method": "heuristic",
  "disclaimer": "合規對應使用啟發式分析自動產生，應由合規專家審查。對應可能未涵蓋所有要求，僅供參考。"
}
```

---

### 工具 11：取得快速參考

**用途**：為特定安全主題生成快速參考指南。提供依優先順序組織的可執行檢查清單（快速成效、必備項目、加分項目）。

**何時使用**：快速決策、向領導層簡報、新團隊成員上線、或建立安全檢查清單。

#### MCP 模式範例（Claude Desktop）：

```
你：「給我 prompt injection 防禦的快速參考」

Claude：[使用 get_quick_reference 工具]
        快速參考：Prompt Injection 防禦

        🚀 快速成效（低成本、高影響）：
        [ ] AID-H-001：Adversarial Robustness Training
            成本：低 | 影響：高
        [ ] AID-H-002：AI-Contextualized Data Sanitization & Input Validation
            成本：低 | 影響：重大

        ⚡ 必備項目（必要防禦）：
        [ ] AID-D-001：Adversarial Input, Prompt Injection & Signal-Authenticity Detection
            成本：中 | 影響：高
        [ ] AID-I-001：AI Execution Sandboxing & Runtime Isolation
            成本：中 | 影響：高
        [ ] AID-H-003：Secure ML Supply Chain Management
            成本：中 | 影響：高

        ✨ 加分項目（額外深度）：
        [ ] AID-D-002：AI Model Anomaly & Performance Drift Detection
            成本：高 | 影響：中
```

#### REST API 範例：

```bash
curl -X POST "http://localhost:8000/api/v1/quick-reference?topic=RAG%20security&format=checklist&max_items=10"
```

**回應：**
```json
{
  "topic": "RAG security",
  "format": "checklist",
  "generated_at": "2025-11-11T12:00:00Z",
  "quick_wins": [
    {
      "priority": 1,
      "technique_id": "AID-H-001",
      "name": "Adversarial Robustness Training",
      "tactic": "Harden",
      "description": "為 RAG 查詢實作基準輸入驗證...",
      "estimated_effort": "Low",
      "estimated_impact": "High"
    }
  ],
  "must_haves": [
    {
      "priority": 1,
      "technique_id": "AID-H-003",
      "name": "Secure ML Supply Chain Management",
      "tactic": "Harden",
      "description": "在傳送至 LLM 前驗證檢索的文件...",
      "estimated_effort": "Medium",
      "estimated_impact": "High"
    }
  ],
  "nice_to_haves": [
    {
      "priority": 1,
      "technique_id": "AID-D-004",
      "name": "AI Artifact, Runtime Configuration, Route & Lifecycle Integrity Monitoring",
      "tactic": "Detect",
      "description": "監控檢索模式以偵測異常...",
      "estimated_effort": "High",
      "estimated_impact": "Medium"
    }
  ],
  "total_items": 10
}
```

---

### 工具 12：取得威脅涵蓋範圍

**用途**：分析已實作防禦技術的威脅涵蓋範圍。給定 AIDEFEND 技術 ID 清單，計算涵蓋哪些威脅（OWASP LLM Top 10 2026、MITRE ATLAS、MAESTRO）並提供涵蓋率。

OWASP LLM coverage array 使用 `LLM03` 這類穩定的裸 rank key；判讀時須搭配 `framework_labels.owasp_llm`，該欄位代表與 active index 原子性綁定的 edition。完成現行同步後，其值為 `OWASP LLM Top 10 2026`。

**何時使用**：追蹤已實作防禦涵蓋哪些威脅、識別涵蓋缺口、向利害關係人報告安全狀態、驗證防禦投資。

#### MCP 模式範例（Claude Desktop）：

```
你：「分析 AID-D-001.001、AID-H-002.001、AID-I-003.004 的威脅涵蓋範圍」

Claude：[使用 get_threat_coverage 工具]
        威脅涵蓋範圍分析

        已分析技術：3
        有效技術：3
        無效技術：0

        ## 依 Framework 的威脅涵蓋範圍

        ### OWASP LLM Top 10 2026
        涵蓋率：50.0%（5/10）
        已涵蓋威脅：LLM01、LLM02、LLM03、LLM05、LLM07

        ## 依技術的涵蓋範圍

        ### AID-D-001.001：Per-Prompt Content, Intent & Obfuscation Analysis
        - OWASP：LLM01

        ### AID-H-002.001：Training & Fine-Tuning Data Sanitization
        - OWASP：LLM02、LLM05

        ### AID-I-003.004：High-Risk Agent Action Containment
        - OWASP：LLM03、LLM07

        此處省略其他 mapped framework 的區段。
```

#### REST API 範例：

```bash
curl -X POST "http://localhost:8000/api/v1/threat-coverage" \
  -H "Content-Type: application/json" \
  -d '{
    "implemented_techniques": ["AID-D-001.001", "AID-H-002.001", "AID-I-003.004"]
  }'
```

**OWASP 相關回應欄位節錄**（省略其他 framework key）：
```json
{
  "input_count": 3,
  "valid_count": 3,
  "invalid_count": 0,
  "invalid_techniques": [],
  "framework_labels": {
    "owasp_llm": "OWASP LLM Top 10 2026"
  },
  "covered": {
    "owasp_llm": ["LLM01", "LLM02", "LLM03", "LLM05", "LLM07"]
  },
  "coverage_rate": {
    "owasp_llm": 0.5
  },
  "by_technique": [
    {
      "technique_id": "AID-D-001.001",
      "technique_name": "Per-Prompt Content, Intent & Obfuscation Analysis",
      "tactic": "Detect",
      "threats_covered": {
        "owasp_llm": ["LLM01"]
      }
    }
  ]
}
```

---

### 工具 13：取得實作計劃

**用途**：基於啟發式評分（威脅重要性、實作難易度、階段權重、支柱權重）取得下一個要實作的防禦技術排名建議。協助優先化安全投資。

**何時使用**：規劃安全路線圖、優先化技術實作、尋找快速成效、證明安全預算、優化縱深防禦策略。

**注意**：此工具僅提供啟發式評分。LLM 應使用這些評分透過 RAG 做出最終建議。

**⚡ 複合工具模式**：使用 `detail_level="standard"`（推薦）或 `detail_level="detailed"` 在單次呼叫中取得前 5 個建議的可執行策略摘要，避免 N+1 的詳細請求序列。

**策略查詢**：
- 使用**聯合邏輯**同時查詢母層與子層策略
- 為來自子技術的策略添加 `context_source` 欄位（協助識別策略來自哪個子技術）
- **絕不自動包含程式碼片段** - 請針對特定技術另外使用 `get_secure_code_snippet`

**參數**：
- `implemented_techniques`（選填）：已實作的技術 ID 列表
- `exclude_tactics`（選填）：要排除的 tactic 列表（例如 ["Model", "Harden"]）
- `top_k`（預設：10）：要返回的建議數量（1-20）
- `detail_level`（預設："basic"）：詳細程度
  - **"basic"**：僅返回技術 ID 和評分（最快，原始行為）
  - **"standard"**：返回前 5 個技術的簡短摘要（200 字元）（大多數情況推薦使用）
  - **"detailed"**：返回前 5 個技術的完整摘要（500 字元）（用於全面規劃）

#### MCP 模式範例（Claude Desktop）：

```
你：「給我一個實作計劃，排除技術 AID-D-001 和 AID-H-002」

Claude：[使用 get_implementation_plan 工具]
        防禦實作計劃

        已實作技術：2
        產生的建議：10

        ## 優先順序分類

        - ⚡ 快速成效（3 個技術）：高分數 + 有開源工具
        - 🎯 高優先順序（5 個技術）：評分 ≥ 7.0
        - 📋 標準（2 個技術）：評分 < 7.0

        ## 頂級建議

        🥇 AID-D-014：RAG Content, Relevance & Retrieval-Provenance Monitoring
           - 評分：8.5/10
           - Tactic：Detect
           - Pillar：Detect | Phase：Development
           - 評分明細：
             - 威脅重要性：3.0/3
             - 實作難易度：2.0/2
             - 階段權重：1.5/2
             - 支柱權重：1.5/2
             - 工具生態系統：0.5/1
           - 理由：涵蓋高風險威脅；有開源工具；偵測增加縱深防禦
           - ✅ 有開源工具

        🥈 AID-H-010：Classifier-Free Guidance Hardening
           - 評分：7.5/10
           - Tactic：Harden
           - Pillar：Prevent | Phase：Design
           - 理由：涵蓋高風險威脅；早期階段實作（Design）

        🥉 AID-I-005：Emergency "Kill-Switch" / AI System Halt
           - 評分：7.0/10
           - Tactic：Isolate
           - Pillar：Prevent | Phase：Development
```

#### REST API 範例 1：基本模式（預設）

```bash
curl -X POST "http://localhost:8000/api/v1/implementation-plan" \
  -H "Content-Type: application/json" \
  -d '{
    "implemented_techniques": ["AID-D-001", "AID-H-002"],
    "exclude_tactics": ["Model"],
    "top_k": 10
  }'
```

**回應：**
```json
{
  "input": {
    "implemented_count": 2,
    "exclude_tactics": ["Model"],
    "top_k": 10,
    "detail_level": "basic"
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
      "reasoning": "涵蓋高風險威脅；有開源工具；偵測增加縱深防禦",
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

#### REST API 範例 2：標準模式（推薦 - 複合工具）

```bash
curl -X POST "http://localhost:8000/api/v1/implementation-plan" \
  -H "Content-Type: application/json" \
  -d '{
    "implemented_techniques": [],
    "exclude_tactics": [],
    "top_k": 5,
    "detail_level": "standard"
  }'
```

**回應：**
```json
{
  "input": {
    "implemented_count": 0,
    "exclude_tactics": [],
    "top_k": 5,
    "detail_level": "standard"
  },
  "recommendations": [
    {
      "rank": 1,
      "technique_id": "AID-D-014",
      "technique_name": "Prompt Injection Detection",
      "score": 8.5,
      ...
    }
  ],
  "categories": {
    "quick_wins": ["AID-D-014"],
    "high_priority": ["AID-D-014", "AID-H-010"],
    "standard": []
  },
  "actionable_strategies": [
    {
      "technique_id": "AID-D-014",
      "technique_name": "Prompt Injection Detection",
      "strategy_count": 3,
      "strategies": [
        {
          "strategy_name": "語意相似度偵測",
          "summary": "使用嵌入向量透過測量使用者輸入與已知攻擊模式之間的語意相似度來偵測 prompt injection。此方法將輸入文字與已知攻擊模式資料庫進行比對..."
        },
        {
          "strategy_name": "基於規則的偵測",
          "summary": "實作模式比對規則以識別常見的注入技術。規則檢查可疑模式，如系統指令、SQL 語法和腳本標籤...",
          "context_source": "直接注入"
        }
      ]
    }
  ],
  "metadata": {
    "compound_tool_enabled": true,
    "detail_level": "standard",
    "strategies_fetched": 5
  },
  "timestamp": "2025-11-12T10:30:00Z"
}
```

**注意**：具有 `context_source` 欄位的策略表示來自子技術。這有助於您理解策略的具體上下文。

**💡 建議工作流程**：
1. 使用 `detail_level="standard"` 取得簡要概覽與 200 字元摘要
2. 向使用者呈現建議
3. 針對使用者選擇的特定技術使用 `get_secure_code_snippet(technique_id, strategy_name)`

這個工作流程可減少請求往返次數。若延遲是營運要求，請在自己的部署環境中測量端到端時間。

---

### 工具 14：分類威脅（雙層本地比對）

**用途**：使用快速本地雙層比對系統在文字中分類威脅：
1. **第一層（靜態關鍵字）**：直接關鍵字比對（即時）
2. **第二層（RapidFuzz 模糊比對）**：經過效能優化的容錯比對

將常見威脅術語（prompt injection、training data poisoning 等）對應至 canonical framework ID（OWASP LLM Top 10 2026、MITRE ATLAS、MAESTRO）。

**何時使用**：標準化事故報告、安全警報、漏洞描述或威脅情報中的威脅關鍵字為標準 framework ID。快速分類安全事件。

**運作方式**：
- 100% 本地處理 - 無外部 API 呼叫，所有處理都在本地進行
- 第一層：先嘗試靜態關鍵字比對（即時精確比對）
- 第二層：如果無靜態比對，使用 RapidFuzz 進行容錯模糊比對
- 總是標示結果來自哪一層（static_keyword、fuzzy_match 或 no_match）
- OWASP LLM classifier claim 一律使用明確、帶 edition 的 2026 ID，例如 `LLM05:2026`；裸 rank 可作為查詢別名，但 classifier 不會把它當成輸出 claim
- `mapping_status` 會分別標示內建 classifier catalog edition 與目前已同步的 active index edition，並指出兩者是否對齊
- 即使某個分類 ID 不存在於 active index，分類結果仍會保留，但會標示為 unresolved，也不會為該 claim 建議以 ID 查詢防禦

**主要功能**：
- **100% 本地與隱私**：零外部 API 呼叫，所有處理在您的機器上
- **免費**：無 API 成本，不消耗 token
- **快速路徑**：RapidFuzz 提供經過效能優化的本地模糊比對
- **離線就緒**：初始設定後完全離線運作

#### MCP 模式範例（Claude Desktop）：

```
你：「分類以下威脅：『我們偵測到繞過輸入驗證的 prompt injection 攻擊』」

Claude：[使用 classify_threat 工具]
        威脅分類結果

        分類來源：🔍 靜態關鍵字比對（第一層）
        輸入文字：我們偵測到繞過輸入驗證的 prompt injection 攻擊
        比對的關鍵字：1

        ## 比對的關鍵字

        🟢 Prompt Injection（主要，信心度：0.98）

        ## 標準化威脅 ID

        OWASP LLM Top 10 2026：LLM01:2026
        MITRE ATLAS：AML.T0051
        MAESTRO：Adversarial Examples (L1)、Goal Misalignment Cascades (Cross-Layer)

        ## 威脅詳情

        - OWASP-LLM01:2026：Prompt Injection
          - 信心度：0.98
          - 比對的關鍵字：prompt injection
          - 比對類型：primary

        ## 建議後續步驟

        - get_defenses_for_threat
          - 參數：{'threat_id': 'LLM01:2026'}
          - 理由：尋找 LLM01:2026 的防禦技術

        - get_quick_reference
          - 參數：{'topic': 'prompt injection', 'max_items': 10}
          - 理由：取得 prompt injection 的可執行緩解步驟
```

#### REST API 範例：

```bash
curl -X POST "http://localhost:8000/api/v1/classify-threat" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Recent training data poisoning attack detected in our ML pipeline",
    "top_k": 5
  }'
```

**回應欄位節錄**（省略其他 ATLAS／MAESTRO 詳情與後續動作）：
```json
{
  "source": "static_keyword",
  "input_text_preview": "Recent training data poisoning attack detected in our ML pipeline",
  "keywords_found": [
    {
      "keyword": "training data poisoning",
      "match_type": "primary",
      "confidence": 0.96
    }
  ],
  "normalized_threats": {
    "owasp": ["LLM05:2026"],
    "atlas": ["AML.T0010", "AML.T0018", "AML.T0020"],
    "maestro": [
      "Data Poisoning (L2)",
      "Data Poisoning (Training Phase) (L1)",
      "Supply Chain Attacks (Cross-Layer)"
    ]
  },
  "threat_details": [
    {
      "threat_id": "OWASP-LLM05:2026",
      "threat_name": "Training Data Poisoning",
      "confidence": 0.96,
      "matched_keyword": "training data poisoning",
      "match_type": "primary",
      "resolvable": true
    }
  ],
  "recommended_actions": [
    {
      "tool": "get_defenses_for_threat",
      "args": {"threat_id": "LLM05:2026"},
      "reason": "Find defense techniques for LLM05:2026"
    }
  ],
  "mapping_status": {
    "all_emitted_claims_resolvable": true,
    "corpus_mapping_available": true,
    "unresolved_claims": [],
    "unmapped_keywords": [],
    "classifier_owasp_llm_edition": "2026",
    "classifier_owasp_llm_label": "OWASP LLM Top 10 2026",
    "active_index_owasp_llm_edition": "2026",
    "active_index_owasp_llm_label": "OWASP LLM Top 10 2026",
    "migration_registry_status": "active",
    "owasp_llm_catalog_aligned": true
  },
  "timestamp": "2026-08-05T10:30:00Z"
}
```

`classifier_owasp_llm_edition` 表示此 MCP build 會輸出的 ID edition；`active_index_owasp_llm_edition` 則表示目前從 AIDEFEND 載入的語料 edition。若 `owasp_llm_catalog_aligned=false`、migration registry 不是 active，或 `unresolved_claims` 非空，應先同步再針對受影響的帶 edition ID 查詢防禦；classifier 不會把 2026 claim 偷換成 legacy 2025 index 的同 rank 項目。

---

### 工具 15：全面搜尋（多查詢聚合）

**用途**：並行執行多個搜尋查詢並智慧聚合結果。自動將廣泛主題展開為特定查詢以達成全面涵蓋。

**何時使用**：廣泛安全主題、研究導向探索、取得安全領域全貌、或不知道確切關鍵字時。

#### MCP 模式範例（Claude Desktop）：

```
你：「告訴我 AIDEFEND 中關於 deepfake 防禦的所有內容」

Claude：[使用 comprehensive_search 工具]
        全面搜尋結果：deepfake defenses

        執行的查詢：3 個並行搜尋
        總結果：15 個唯一技術

        查詢 1：「deepfake detection」（5 個結果）
        查詢 2：「synthetic media defense」（5 個結果）
        查詢 3：「media authenticity」（5 個結果）

        頂級技術：
        1. AID-D-008：Secondary AI Defender Fusion & Assurance（評分：0.92）
        2. AID-H-015：Certified Defenses（評分：0.88）
        3. AID-D-009：Fact Assurance & Multi-Agent Hallucination Detection（評分：0.85）
        ...
```

#### REST API 範例：

```bash
curl -X POST "http://localhost:8000/api/v1/comprehensive-search" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "RAG security best practices",
    "max_results": 20
  }'
```

**回應：**
```json
{
  "topic": "RAG security best practices",
  "queries_executed": 4,
  "total_results": 18,
  "query_breakdown": [
    {
      "query": "retrieval augmented generation security",
      "results_count": 6
    },
    {
      "query": "vector database security",
      "results_count": 5
    },
    {
      "query": "document injection prevention",
      "results_count": 4
    },
    {
      "query": "RAG prompt safety",
      "results_count": 3
    }
  ],
  "aggregated_results": [
    {
      "technique_id": "AID-H-003",
      "name": "Secure ML Supply Chain Management",
      "tactic": "Harden",
      "relevance_score": 0.91,
      "matched_queries": ["retrieval augmented generation security", "document injection prevention"]
    }
  ]
}
```

---

### 工具 16：分析安全狀態

**用途**：整合技術涵蓋範圍、威脅 framework 涵蓋範圍和可執行建議的統一安全狀態分析。全面安全評估的一站式工具。

**何時使用**：執行層報告、安全方案評估、季度審查、或建立安全基準。

#### MCP 模式範例（Claude Desktop）：

```
你：「分析我的安全狀態。我已實作：AID-H-001、AID-H-002、AID-D-001、AID-I-001」

Claude：[使用 analyze_security_posture 工具]
        安全狀態分析

        整體評估：發展中
        已實作技術：4

        ## 技術涵蓋範圍
        - 涵蓋率：1.3%（4/300 個可執行控制）
        - 依 Tactic：
          • Harden：11%（2/18）⚠️
          • Detect：8%（1/12）⚠️
          • Isolate：12.5%（1/8）⚠️

        ## 威脅 Framework 涵蓋範圍
        - OWASP LLM Top 10 2026：40%（已涵蓋 4/10 個威脅）
        - MITRE ATLAS：7%（已涵蓋 3/43 個威脅）
        - MAESTRO：15%（已涵蓋 2/13 個威脅）

        ## 關鍵洞察
        - ✅ Harden tactic 有良好基礎
        - ⚠️ 偵測能力有限
        - ❌ 無 Model 強化技術
        - ⚠️ ATLAS 涵蓋率低

        ## 優先事項
        1. 實作 AID-D-002（Anomaly Detection）- 填補偵測缺口
        2. 實作 AID-M-001（AI Asset Inventory & Mapping）- 解決 Model tactic 缺口
        3. 涵蓋頂級 ATLAS 威脅：AML.T0043、AML.T0020
```

#### REST API 範例：

```bash
curl -X POST "http://localhost:8000/api/v1/analyze-security-posture" \
  -H "Content-Type: application/json" \
  -d '{
    "implemented_techniques": ["AID-H-001", "AID-H-002", "AID-D-001", "AID-I-001"],
    "view": "both",
    "system_type": "rag"
  }'
```

**回應：**
```json
{
  "implemented_count": 4,
  "summary": {
    "overall_posture": "developing",
    "key_insights": [
      "Harden tactic 有良好基礎",
      "偵測能力有限",
      "無 Model 強化技術"
    ],
    "top_priorities": [
      "實作 AID-D-002（Anomaly Detection）",
      "實作 AID-M-001（AI Asset Inventory & Mapping）"
    ]
  },
  "technical_coverage": {
    "overall_coverage": {
      "percentage": 25.0,
      "implemented": 4,
      "total": 300
    },
    "by_tactic": [
      {"tactic": "Harden", "percentage": 11.1, "implemented": 2, "total": 18}
    ],
    "critical_gaps": [
      {"technique_id": "AID-M-001", "name": "AI Asset Inventory & Mapping", "tactic": "Model"}
    ]
  },
  "threat_coverage": {
    "coverage_rate": {
      "owasp": 0.4,
      "atlas": 0.07,
      "maestro": 0.15
    },
    "covered_threats": {
      "owasp": ["LLM01", "LLM02", "LLM03", "LLM05"],
      "atlas": ["AML.T0020", "AML.T0043", "AML.T0051"]
    },
    "uncovered_threats": {
      "owasp": ["LLM04", "LLM06", "LLM07", "LLM08", "LLM09", "LLM10"]
    }
  }
}
```

---

### 工具 17：比較技術

**用途**：多個 AIDEFEND 技術的並排比較，含啟發式評分（效能、複雜度、成本）。協助做出明智的實作決策。

**何時使用**：技術選擇、預算優先化、理解取捨、或教育利害關係人。

**100% 本地處理** - 所有評分使用基於 metadata 的啟發式演算法，無外部 API 呼叫。

#### MCP 模式範例（Claude Desktop）：

```
你：「比較 AID-H-001、AID-D-001 和 AID-I-001。我應該先實作哪一個？」

Claude：[使用 compare_techniques 工具]
        技術比較矩陣

        已比較技術：3

        ## 摘要統計

        - 平均效能：75.0/100
        - 平均複雜度：45.0/100
        - 平均成本：38.0/100

        ## 比較矩陣

        | 技術 | 效能 | 複雜度 | 成本 |
        |------|------|--------|------|
        | AID-H-001 | 85/100 | 35/100 | 30/100 |
        | AID-D-001 | 75/100 | 50/100 | 40/100 |
        | AID-I-001 | 65/100 | 50/100 | 45/100 |

### 評分邏輯 (情境感知)

- **效能 (Effectiveness, 0-100)**:
  - **預防加分 (Prevention Bonus, +25)**：預防性控制 (hardening, filters) 比偵測性控制得分更高。
  - **資產重要性 (Asset Criticality, +15)**：保護關鍵資產（如模型權重或訓練資料）會有額外加分。
  - **可驗證性 (Validation Ready, +10)**：如果技術是可驗證/可測試的，會獲得額外加分。
  - **威脅覆蓋 (Threat Coverage)**：覆蓋每個 OWASP/ATLAS/MAESTRO 威脅都會獲得分數。

- **複雜度 (Complexity, 0-100)**:
  - **跨域摩擦 (Cross-Domain Friction)**：需要跨團隊協調（例如 DevOps + Data Science）的技術會有更高的複雜度。
  - **人為規模 (Human Scale)**：流程繁重的技術（訓練、政策）會有更高的複雜度。
  - **整合階段 (Integration Phase)**：「建置」階段的技術被評為比執行時部署更複雜。

- **成本 (Cost, 0-100)**:
  - **營運支出 vs 資本支出 (OpEx vs CapEx)**：「偵測」技術的營運支出分數（日誌、警報）高於「預防」（設定後不理）。
  - **雲端成本 (Cloud Costs)**：雲原生技術包含預估的基礎設施成本。
  - **工具成本 (Tooling)**：商業工具會增加成本；純開源會降低成本。

        ## 實作建議

        ### 快速成效
        - AID-H-001：高效能（85）、低複雜度（35）、低成本（30）

        ### 實作優先順序（依效能/複雜度比率）
        1. AID-H-001（比率：2.43）⭐ 最高投資報酬率
        2. AID-D-001（比率：1.50）
        3. AID-I-001（比率：1.30）

        建議：從 AID-H-001 開始以快速產生影響！
```

#### REST API 範例：

```bash
curl -X POST "http://localhost:8000/api/v1/compare-techniques" \
  -H "Content-Type: application/json" \
  -d '{
    "technique_ids": ["AID-H-001", "AID-D-001", "AID-I-001"],
    "include_recommendations": true
  }'
```

**回應：**
```json
{
  "input_techniques": ["AID-H-001", "AID-D-001", "AID-I-001"],
  "comparison_matrix": [
    {
      "source_id": "AID-H-001",
      "name": "Adversarial Robustness Training",
      "tactic": "Harden",
      "effectiveness_score": 85,
      "complexity_score": 35,
      "cost_score": 30,
      "threat_coverage": {
        "owasp": 3,
        "atlas": 2,
        "maestro": 1
      },
      "has_implementation_strategies": true,
      "has_code_snippets": true,
      "has_opensource_tools": true
    }
  ],
  "summary": {
    "techniques_compared": 3,
    "average_effectiveness": 75.0,
    "average_complexity": 45.0,
    "average_cost": 38.3
  },
  "recommendations": [
    {
      "category": "快速成效",
      "description": "高效能、低複雜度、低成本",
      "techniques": [
        {"id": "AID-H-001", "name": "Adversarial Robustness Training"}
      ]
    }
  ]
}
```

---

### 工具 18：生成事故處理手冊

**用途**：為 AI 安全事故生成結構化事故回應手冊。提供遵循 NIST 事故回應階段的基於時間軸的行動計劃。

**何時使用**：主動事故回應、IR 規劃、訓練教材、或安全營運手冊開發。

**100% 本地處理** - 整合本地 classify_threat 和 get_defenses_for_threat 工具，無外部 API 呼叫。

#### MCP 模式範例（Claude Desktop）：

```
你：「我們偵測到繞過驗證的可疑 prompt injection 嘗試。生成事故處理手冊。」

Claude：[使用 generate_incident_playbook 工具]
        🚨 事故回應手冊

        識別的主要威脅：OWASP-LLM01:2026（Prompt Injection）
        信心度：98%
        總行動項目：23

        ## 立即行動（0-15 分鐘）

        1. 🔴 啟動事故回應團隊
           優先順序：重大
           時間：2-5 分鐘

        2. 🔴 隔離受影響的 LLM 端點
           優先順序：重大
           時間：5 分鐘
           說明：暫時停用或限流受影響端點

        ## 調查（15 分鐘 - 2 小時）

        1. 🟠 執行威脅分類
           優先順序：高
           時間：10-15 分鐘
           工具：classify_threat 工具

        2. 🟠 收集 IOC
           優先順序：高
           時間：20-30 分鐘
           說明：收集 IP 位址、使用者 ID、時間戳、請求模式

        ## 遏制（2-8 小時）

        1. 🔴 部署防禦：AID-H-001（Adversarial Robustness Training）
           優先順序：高
           時間：1-3 小時

        2. 🔴 部署防禦：AID-H-002（AI-Contextualized Data Sanitization & Input Validation）
           優先順序：高
           時間：1-3 小時

        ## 復原與補救（8+ 小時）

        1. 🟠 實作安全控制
           優先順序：高
           時間：4-8 小時
           參考：參閱遏制階段的防禦技術

        2. 🟡 進行事故後檢討
           優先順序：中
           時間：2-3 小時
```

#### REST API 範例：

```bash
curl -X POST "http://localhost:8000/api/v1/generate-incident-playbook" \
  -H "Content-Type: application/json" \
  -d '{
    "incident_description": "Production LLM API showing unusual outputs. Users report getting responses that reveal internal system prompts and training data. Attack patterns from multiple IPs.",
    "include_defense_techniques": true
  }'
```

**回應：**
```json
{
  "incident_summary": {
    "description": "Production LLM API showing unusual outputs...",
    "total_action_items": 23,
    "estimated_total_time": "1-3 天",
    "primary_threat": {
      "threat_id": "OWASP-LLM01:2026",
      "framework": "OWASP",
      "description": "Prompt Injection",
      "confidence": 98.0
    }
  },
  "timeline": {
    "immediate": {
      "phase": "立即行動",
      "timeframe": "0-15 分鐘",
      "objective": "初始回應、證據保全與遏制",
      "actions": [
        {
          "action": "啟動事故回應團隊",
          "priority": "CRITICAL",
          "description": "通知指定的 IR 團隊成員",
          "estimated_time": "2-5 分鐘"
        },
        {
          "action": "隔離受影響的 LLM 端點",
          "priority": "CRITICAL",
          "description": "暫時停用或限流受影響的 LLM API 端點",
          "estimated_time": "5 分鐘"
        }
      ]
    },
    "investigation": {
      "phase": "調查",
      "timeframe": "15 分鐘 - 2 小時",
      "actions": []
    },
    "containment": {
      "phase": "遏制",
      "timeframe": "2-8 小時",
      "actions": []
    },
    "recovery": {
      "phase": "復原與補救",
      "timeframe": "8+ 小時",
      "actions": []
    }
  },
  "defense_techniques": {
    "techniques": [
      {
        "source_id": "AID-H-001",
        "name": "Adversarial Robustness Training",
        "tactic": "Harden",
        "description": "實作強健的輸入驗證..."
      },
      {
        "source_id": "AID-H-002",
        "name": "AI-Contextualized Data Sanitization & Input Validation",
        "tactic": "Harden",
        "description": "部署 prompt injection 偵測..."
      }
    ]
  },
  "generated_at": "2025-01-18T10:30:00Z"
}
```

---

## 額外資源

- **API 文件**：http://localhost:8000/docs（當服務執行時）
- **主要 README**：[README-繁體中文.md](../README-繁體中文.md)
- **安裝指南**：[INSTALL-繁體中文.md](../INSTALL-繁體中文.md)
- **設定指南**：[CONFIGURATION.md](CONFIGURATION.md)
- **安全政策**：[SECURITY.md](../SECURITY.md)
