# GPU Acceleration Guide (Optional) | GPU 加速指南（選用）

> **Note**: GPU acceleration is **completely optional**. The AIDEFEND MCP Service runs well on CPU-only environments (500-1000ms per query). This guide is for advanced users seeking 3-5x performance improvement in production deployments.

> **注意**：GPU 加速是**完全選用的功能**。AIDEFEND MCP 服務在純 CPU 環境下運作良好（每次查詢 500-1000ms）。本指南適用於需要在生產環境中提升 3-5 倍效能的進階使用者。

---

## Performance Impact | 效能影響

**CPU-only (default - no setup required):**
- Single search: 500-1000ms ✅ Works out-of-the-box
- Comprehensive search (5 queries): 2-5 seconds
- Suitable for: Development, personal use, moderate workloads

**CPU 模式（預設 - 無需設定）：**
- 單次搜尋：500-1000ms ✅ 開箱即用
- 綜合搜尋（5 個查詢）：2-5 秒
- 適用於：開發、個人使用、中等負載

**GPU-accelerated (optional - requires setup):**
- Single search: 100-300ms ⚡ 3-5x faster
- Comprehensive search (5 queries): 0.5-1.5 seconds
- Suitable for: Production, high-volume deployments, enterprise

**GPU 加速模式（選用 - 需要設定）：**
- 單次搜尋：100-300ms ⚡ 快 3-5 倍
- 綜合搜尋（5 個查詢）：0.5-1.5 秒
- 適用於：生產環境、高流量部署、企業級應用

**Decision**: Only pursue GPU acceleration if you have GPU hardware and need sub-second query latency.

**決策建議**：只有在你擁有 GPU 硬體且需要低於 1 秒的查詢延遲時，才需要啟用 GPU 加速。

---

## Prerequisites | 前置需求

### Hardware Requirements | 硬體需求

**One of:**
- ✅ **NVIDIA GPU** (Windows, Linux) - CUDA support
- ✅ **AMD GPU** (Windows, Linux) - ROCm support (experimental)
- ✅ **Apple Silicon** (macOS) - Metal Performance Shaders (MPS)
- ✅ **Intel GPU** (Windows, Linux) - OpenVINO (experimental)

**以下其中一種：**
- ✅ **NVIDIA GPU**（Windows、Linux）- 支援 CUDA
- ✅ **AMD GPU**（Windows、Linux）- 支援 ROCm（實驗性）
- ✅ **Apple Silicon**（macOS）- Metal Performance Shaders (MPS)
- ✅ **Intel GPU**（Windows、Linux）- OpenVINO（實驗性）

**Minimum specs:**
- GPU memory: 2GB+
- Driver: Latest version recommended

**最低規格：**
- GPU 記憶體：2GB 以上
- 驅動程式：建議使用最新版本

### Software Requirements | 軟體需求

Varies by platform (see platform-specific sections below).

依平台而異（請參閱下方各平台專屬章節）。

---

## Platform-Specific Setup | 各平台設定指南

### Windows (NVIDIA CUDA) | Windows（NVIDIA CUDA）

#### 1. Check GPU Availability | 檢查 GPU 可用性

```powershell
# Open PowerShell
# 開啟 PowerShell
nvidia-smi
```

Expected output: GPU information and driver version.

預期輸出：GPU 資訊和驅動程式版本。

If command fails: Install NVIDIA drivers from https://www.nvidia.com/Download/index.aspx

如果指令失敗：請從 https://www.nvidia.com/Download/index.aspx 安裝 NVIDIA 驅動程式

#### 2. Install CUDA Toolkit | 安裝 CUDA Toolkit

1. Download CUDA Toolkit 12.x:
   - https://developer.nvidia.com/cuda-downloads
   - Select: Windows → x86_64 → 12 → exe (local)

1. 下載 CUDA Toolkit 12.x：
   - https://developer.nvidia.com/cuda-downloads
   - 選擇：Windows → x86_64 → 12 → exe (local)

2. Install with default settings

2. 使用預設設定安裝

3. Verify:
   ```powershell
   nvcc --version
   ```

3. 驗證：
   ```powershell
   nvcc --version
   ```

#### 3. Install cuDNN | 安裝 cuDNN

1. Download cuDNN v8.x for CUDA 12.x:
   - https://developer.nvidia.com/cudnn
   - Requires free NVIDIA Developer account

1. 下載適用於 CUDA 12.x 的 cuDNN v8.x：
   - https://developer.nvidia.com/cudnn
   - 需要免費的 NVIDIA 開發者帳號

2. Extract and copy files:
   ```powershell
   # Extract to C:\tools\cudnn
   # Copy DLLs to CUDA installation
   # 解壓縮到 C:\tools\cudnn
   # 複製 DLL 檔案到 CUDA 安裝目錄
   xcopy C:\tools\cudnn\bin\*.dll "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.x\bin\" /y
   xcopy C:\tools\cudnn\include\*.h "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.x\include\" /y
   xcopy C:\tools\cudnn\lib\*.lib "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.x\lib\x64\" /y
   ```

2. 解壓縮並複製檔案：（請參閱上方指令）

3. Add to PATH (if not already):
   ```
   C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.x\bin
   ```

3. 加入 PATH 環境變數（如果尚未加入）：
   ```
   C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.x\bin
   ```

#### 4. Install ONNX Runtime GPU | 安裝 ONNX Runtime GPU

```bash
pip uninstall onnxruntime  # Remove CPU version | 移除 CPU 版本
pip install onnxruntime-gpu==1.17.0
```

#### 5. Verify | 驗證

```bash
python -c "import onnxruntime as ort; print(ort.get_available_providers())"
# Expected: ['CUDAExecutionProvider', 'CPUExecutionProvider', ...]
# 預期輸出：['CUDAExecutionProvider', 'CPUExecutionProvider', ...]
```

---

### Linux (NVIDIA CUDA) | Linux（NVIDIA CUDA）

#### 1. Check GPU Availability | 檢查 GPU 可用性

```bash
nvidia-smi
```

If command fails:

如果指令失敗：

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install nvidia-driver-535

# RHEL/CentOS/Fedora
sudo dnf install nvidia-driver
```

#### 2. Install CUDA Toolkit | 安裝 CUDA Toolkit

**Ubuntu/Debian:**
```bash
# Add NVIDIA package repository
# 加入 NVIDIA 套件庫
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-ubuntu2204.pin
sudo mv cuda-ubuntu2204.pin /etc/apt/preferences.d/cuda-repository-pin-600
wget https://developer.download.nvidia.com/compute/cuda/12.3.0/local_installers/cuda-repo-ubuntu2204-12-3-local_12.3.0-545.23.06-1_amd64.deb
sudo dpkg -i cuda-repo-ubuntu2204-12-3-local_12.3.0-545.23.06-1_amd64.deb
sudo cp /var/cuda-repo-ubuntu2204-12-3-local/cuda-*-keyring.gpg /usr/share/keyrings/
sudo apt update
sudo apt install cuda-toolkit-12-3
```

**RHEL/CentOS/Fedora:**
```bash
sudo dnf config-manager --add-repo https://developer.download.nvidia.com/compute/cuda/repos/rhel9/x86_64/cuda-rhel9.repo
sudo dnf install cuda-toolkit-12-3
```

**Verify: | 驗證：**
```bash
nvcc --version
```

#### 3. Install cuDNN | 安裝 cuDNN

```bash
# Download cuDNN from https://developer.nvidia.com/cudnn
# Extract and copy
# 從 https://developer.nvidia.com/cudnn 下載 cuDNN
# 解壓縮並複製
tar -xvf cudnn-linux-x86_64-8.x.x.x_cudaX.Y-archive.tar.xz
sudo cp cudnn-*-archive/include/cudnn*.h /usr/local/cuda/include
sudo cp -P cudnn-*-archive/lib/libcudnn* /usr/local/cuda/lib64
sudo chmod a+r /usr/local/cuda/include/cudnn*.h /usr/local/cuda/lib64/libcudnn*
```

#### 4. Update LD_LIBRARY_PATH | 更新 LD_LIBRARY_PATH

```bash
# Add to ~/.bashrc or ~/.zshrc
# 加入到 ~/.bashrc 或 ~/.zshrc
export PATH=/usr/local/cuda/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH
```

Reload: | 重新載入：
```bash
source ~/.bashrc
```

#### 5. Install ONNX Runtime GPU | 安裝 ONNX Runtime GPU

```bash
pip uninstall onnxruntime
pip install onnxruntime-gpu==1.17.0
```

#### 6. Verify | 驗證

```bash
python -c "import onnxruntime as ort; print(ort.get_available_providers())"
```

---

### macOS (Apple Silicon - Metal) | macOS（Apple Silicon - Metal）

> **Note**: For Intel-based Macs, GPU acceleration is limited. Consider using CPU-only or cloud deployment.

> **注意**：Intel 架構的 Mac 的 GPU 加速功能有限。建議使用純 CPU 模式或雲端部署。

#### 1. Check Apple Silicon | 檢查 Apple Silicon

```bash
uname -m
# Expected: arm64 (Apple Silicon)
# If x86_64: Intel Mac - GPU acceleration not recommended
# 預期：arm64（Apple Silicon）
# 如果是 x86_64：Intel Mac - 不建議使用 GPU 加速
```

#### 2. Install ONNX Runtime with CoreML | 安裝支援 CoreML 的 ONNX Runtime

```bash
pip uninstall onnxruntime
pip install onnxruntime-silicon==1.17.0  # Optimized for Apple Silicon | 針對 Apple Silicon 最佳化
```

**Alternative (broader compatibility): | 替代方案（更廣泛的相容性）：**
```bash
pip install onnxruntime==1.17.0  # Includes CoreML provider | 包含 CoreML 提供者
```

#### 3. Verify | 驗證

```bash
python -c "import onnxruntime as ort; print(ort.get_available_providers())"
# Expected: ['CoreMLExecutionProvider', 'CPUExecutionProvider']
# 預期：['CoreMLExecutionProvider', 'CPUExecutionProvider']
```

#### 4. Enable Metal Performance Shaders (Optional) | 啟用 Metal Performance Shaders（選用）

For maximum performance, ensure Metal is available:

為獲得最佳效能，請確認 Metal 可用：

```bash
python -c "import platform; print(platform.processor())"
# Expected: arm
# 預期：arm
```

---

## Service Configuration | 服務設定

The service is **already configured** to use GPU if available. No code changes needed!

服務**已經預先設定好**在 GPU 可用時自動使用。無需修改任何程式碼！

**In `app/core.py` (lines 293-320): | 在 `app/core.py`（第 293-320 行）：**

```python
# Automatically tries GPU first, falls back to CPU
# 自動優先嘗試使用 GPU，如果失敗則回退到 CPU
self._model = TextEmbedding(
    model_name=resolved_model_name,
    providers=["CUDAExecutionProvider", "CPUExecutionProvider"]  # Windows/Linux
    # On macOS: ["CoreMLExecutionProvider", "CPUExecutionProvider"]
    # 在 macOS 上：["CoreMLExecutionProvider", "CPUExecutionProvider"]
)
```

The service will: | 服務會執行以下動作：
1. Try GPU execution first | 1. 優先嘗試使用 GPU 執行
2. Automatically fall back to CPU if GPU unavailable | 2. 如果 GPU 無法使用，自動回退到 CPU
3. Log which provider is being used | 3. 記錄目前使用的執行提供者

---

## Verification | 驗證

### 1. Check Logs on Startup | 啟動時檢查日誌

**GPU detected: | GPU 偵測成功：**
```
INFO: ✅ Embedding model loaded with GPU acceleration (CUDA)
INFO: ✅ Embedding 模型已載入並啟用 GPU 加速 (CUDA)
```

**CPU fallback: | CPU 回退模式：**
```
WARNING: ⚠️  Embedding model loaded with CPU (provider: CPUExecutionProvider)
INFO: For faster performance, see docs/advanced/GPU_ACCELERATION.md
WARNING: ⚠️  Embedding 模型已使用 CPU 載入（提供者：CPUExecutionProvider）
INFO: 若要提升效能，請參閱 docs/advanced/GPU_ACCELERATION.md
```

### 2. Run Benchmark | 執行效能測試

```bash
python scripts/benchmark_search.py
```

**Expected results with GPU: | GPU 模式預期結果：**
```
============================================================
BENCHMARK RESULTS
============================================================
Query: 'prompt injection attacks'
Total search time: 185.42 ms (0.1854 s)
Performance: ✅ EXCELLENT (< 500ms)
============================================================
```

**Expected results with CPU: | CPU 模式預期結果：**
```
Total search time: 687.23 ms (0.6872 s)
Performance: ✓ GOOD (< 1s)
```

### 3. Monitor GPU Usage | 監控 GPU 使用率

**Windows:**
```powershell
nvidia-smi -l 1  # Update every 1 second | 每 1 秒更新一次
```

**Linux:**
```bash
watch -n 1 nvidia-smi
```

**macOS:**
```bash
sudo powermetrics --samplers gpu_power -i 1000
```

During queries, you should see GPU utilization increase.

執行查詢時，你應該會看到 GPU 使用率上升。

---

## Troubleshooting | 疑難排解

### GPU Not Detected | GPU 未偵測到

**Symptom**: Logs show CPU provider despite GPU installation

**症狀**：即使已安裝 GPU，日誌仍顯示使用 CPU 提供者

**Checks: | 檢查項目：**

1. **Verify ONNX Runtime GPU: | 驗證 ONNX Runtime GPU：**
   ```bash
   python -c "import onnxruntime as ort; print(ort.get_available_providers())"
   ```
   Should include `CUDAExecutionProvider` (NVIDIA) or `CoreMLExecutionProvider` (Apple)

   應該包含 `CUDAExecutionProvider`（NVIDIA）或 `CoreMLExecutionProvider`（Apple）

2. **Check CUDA paths (NVIDIA only): | 檢查 CUDA 路徑（僅限 NVIDIA）：**
   ```bash
   # Windows
   echo %CUDA_PATH%

   # Linux
   echo $LD_LIBRARY_PATH
   ```

3. **Reinstall ONNX Runtime: | 重新安裝 ONNX Runtime：**
   ```bash
   pip uninstall onnxruntime onnxruntime-gpu onnxruntime-silicon
   # Then reinstall the appropriate version for your platform
   # 然後為你的平台重新安裝適當的版本
   ```

### CUDA Out of Memory | CUDA 記憶體不足

**Symptom**: `CUDA out of memory` error

**症狀**：`CUDA out of memory` 錯誤

**Solutions: | 解決方案：**
1. Close other GPU applications | 1. 關閉其他使用 GPU 的應用程式
2. Use smaller embedding model: | 2. 使用較小的 embedding 模型：
   ```bash
   # In .env | 在 .env 中
   EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
   EMBEDDING_DIMENSION=384
   ```
3. Restart service to clear GPU memory | 3. 重新啟動服務以清除 GPU 記憶體

### cuDNN Not Found (Windows/Linux) | 找不到 cuDNN（Windows/Linux）

**Symptom**: `Could not locate cudnn_ops_infer64_8.dll` or `libcudnn.so.8`

**症狀**：`Could not locate cudnn_ops_infer64_8.dll` 或 `libcudnn.so.8`

**Solution: | 解決方案：**
1. Re-download cuDNN for your CUDA version | 1. 重新下載對應你 CUDA 版本的 cuDNN
2. Verify DLL/SO files copied to correct location | 2. 驗證 DLL/SO 檔案已複製到正確位置
3. Restart terminal to reload PATH/LD_LIBRARY_PATH | 3. 重新啟動終端機以重新載入 PATH/LD_LIBRARY_PATH

### Poor Performance Despite GPU | GPU 效能不如預期

**Symptom**: GPU detected but no speed improvement

**症狀**：已偵測到 GPU 但速度沒有改善

**Checks: | 檢查項目：**

1. **GPU actually being used? | GPU 是否真正被使用？**
   ```bash
   # Run benchmark and simultaneously check GPU usage
   # 執行效能測試並同時檢查 GPU 使用率
   nvidia-smi -l 1  # Should show GPU utilization during query
                    # 在查詢期間應該會顯示 GPU 使用率
   ```

2. **Thermal throttling? | 熱節流？**
   ```bash
   nvidia-smi  # Check GPU temperature | 檢查 GPU 溫度
   # If >80°C, improve cooling | 如果超過 80°C，請改善散熱
   ```

3. **LanceDB index created? | LanceDB 索引是否已建立？**
   ```bash
   python scripts/create_lancedb_index.py
   ```

---

## Performance Comparison | 效能比較

### Benchmark Results (Intel Core i9 + RTX 3080) | 效能測試結果（Intel Core i9 + RTX 3080）

| Configuration 設定 | Single Query 單次查詢 | 5 Parallel Queries 5 個平行查詢 | Improvement 改善幅度 |
|-------------------|---------------------|-------------------------------|-------------------|
| CPU only 純 CPU | 687ms | 3.2s | Baseline 基準 |
| GPU (CUDA) | 185ms | 0.8s | **3.7x faster 快 3.7 倍** |
| GPU + Index | 142ms | 0.6s | **4.8x faster 快 4.8 倍** |

### Benchmark Results (Apple M2 Max) | 效能測試結果（Apple M2 Max）

| Configuration 設定 | Single Query 單次查詢 | 5 Parallel Queries 5 個平行查詢 | Improvement 改善幅度 |
|-------------------|---------------------|-------------------------------|-------------------|
| CPU only 純 CPU | 523ms | 2.4s | Baseline 基準 |
| CoreML | 198ms | 0.9s | **2.6x faster 快 2.6 倍** |
| CoreML + Index | 156ms | 0.7s | **3.4x faster 快 3.4 倍** |

---

## Production Deployment | 生產環境部署

### Quick Decision Tree | 快速決策樹

```
Do you have GPU hardware? | 你有 GPU 硬體嗎？
├─ No → Use CPU-only (works great, no setup needed)
│        使用純 CPU（運作良好，無需設定）
└─ Yes 有
    ├─ Personal use / <100 queries/day → CPU probably sufficient
    │   個人使用 / 每天 <100 次查詢 → CPU 可能就足夠
    └─ Production / >1000 queries/day → Set up GPU acceleration
        生產環境 / 每天 >1000 次查詢 → 設定 GPU 加速
        ├─ NVIDIA GPU → Follow Windows/Linux CUDA setup
        │               遵循 Windows/Linux CUDA 設定步驟
        ├─ Apple Silicon → Follow macOS CoreML setup
        │                  遵循 macOS CoreML 設定步驟
        └─ AMD/Intel → Experimental, contact maintainer
                       實驗性功能，請聯絡維護者
```

### Deployment Checklist (GPU-Accelerated) | 部署檢查清單（GPU 加速）

**NVIDIA (Windows/Linux):**
- [ ] NVIDIA drivers installed (latest) | NVIDIA 驅動程式已安裝（最新版）
- [ ] CUDA Toolkit 12.x installed | CUDA Toolkit 12.x 已安裝
- [ ] cuDNN 8.x installed | cuDNN 8.x 已安裝
- [ ] `onnxruntime-gpu` installed | `onnxruntime-gpu` 已安裝
- [ ] `nvidia-smi` shows GPU during queries | `nvidia-smi` 在查詢期間顯示 GPU 使用
- [ ] Logs show "GPU acceleration (CUDA)" | 日誌顯示「GPU acceleration (CUDA)」

**Apple Silicon (macOS):**
- [ ] `onnxruntime-silicon` or `onnxruntime` installed | `onnxruntime-silicon` 或 `onnxruntime` 已安裝
- [ ] Logs show "CoreML" provider | 日誌顯示「CoreML」提供者
- [ ] Benchmark shows 2-3x improvement | 效能測試顯示 2-3 倍改善

**Common (All Platforms): | 通用（所有平台）：**
- [ ] LanceDB index created (`python scripts/create_lancedb_index.py`) | LanceDB 索引已建立
- [ ] Benchmark confirms expected performance | 效能測試確認預期效能
- [ ] GPU memory sufficient (2GB+ free during queries) | GPU 記憶體充足（查詢期間至少 2GB 可用）

---

## Cost-Benefit Analysis | 成本效益分析

### When GPU Makes Sense | 何時應該使用 GPU

✅ **Good candidates: | 適合的情境：**
- Production deployments (>1000 queries/day) | 生產環境部署（每天 >1000 次查詢）
- Real-time applications (need <200ms latency) | 即時應用（需要 <200ms 延遲）
- Enterprise environments (already have GPU infrastructure) | 企業環境（已有 GPU 基礎設施）
- Multi-tenant services (many concurrent users) | 多租戶服務（多個並行使用者）

❌ **Not worth it: | 不值得的情境：**
- Development / testing (CPU is fine) | 開發 / 測試（CPU 就足夠）
- Personal use (<100 queries/day) | 個人使用（每天 <100 次查詢）
- No GPU hardware available (don't buy GPU just for this) | 沒有 GPU 硬體（不要為此專門購買 GPU）
- Budget constraints (cloud GPU instances are expensive) | 預算限制（雲端 GPU 實例很昂貴）

### Alternative: Optimize Without GPU | 替代方案：不使用 GPU 的最佳化

If GPU setup is too complex, consider:

如果 GPU 設定太複雜，可以考慮：

1. **Create LanceDB index** (2-5x improvement, no hardware needed):
   **建立 LanceDB 索引**（改善 2-5 倍，無需額外硬體）：
   ```bash
   python scripts/create_lancedb_index.py
   ```

2. **Use smaller embedding model** (2x faster, slight accuracy trade-off):
   **使用較小的 embedding 模型**（快 2 倍，略微犧牲準確度）：
   ```bash
   # In .env | 在 .env 中
   EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
   EMBEDDING_DIMENSION=384
   ```

3. **Scale horizontally** (multiple instances + load balancer):
   **水平擴展**（多個實例 + 負載平衡器）：
   - Deploy 3x instances → 3x throughput | 部署 3 個實例 → 3 倍吞吐量
   - Cheaper than GPU in some cloud environments | 在某些雲端環境中比 GPU 便宜

---

## References | 參考資料

- **ONNX Runtime GPU**: https://onnxruntime.ai/docs/execution-providers/
- **CUDA Toolkit**: https://developer.nvidia.com/cuda-toolkit
- **cuDNN**: https://developer.nvidia.com/cudnn
- **FastEmbed**: https://github.com/qdrant/fastembed
- **Benchmark Script 效能測試腳本**: [../../scripts/benchmark_search.py](../../scripts/benchmark_search.py)

---

**Maintainer 維護者**: [Edward Lee](https://github.com/edward-playground)
**Last Updated 最後更新**: 2025-11-19
