# GPU Acceleration Status | GPU 加速狀態

## English

AIDEFEND MCP 1.3.0 supports CPU inference only. The supported runtime is
`fastembed==0.8.0` with the CPU `onnxruntime` dependency declared by the
project. A fresh installation requires no GPU, CUDA, ROCm, or platform-specific
accelerator setup.

GPU acceleration is not an installation option or supported deployment mode
for this release. The `fastembed` and `fastembed-gpu` distributions are
mutually exclusive, as are `onnxruntime` and `onnxruntime-gpu`. Replacing one
package in the supported CPU environment would therefore create a different
dependency contract that has not been engineered or tested by this project.

Do not replace the declared CPU packages with GPU variants when installing
AIDEFEND MCP 1.3.0. A future GPU-capable release would need a separate,
conflict-free dependency path plus installation, model, platform, fallback,
and end-to-end test coverage before it could be documented as supported.

For supported performance tuning, use the CPU and LanceDB guidance in the
[Performance Optimization Summary](../PERFORMANCE_OPTIMIZATION.md).

## 繁體中文

AIDEFEND MCP 1.3.0 僅支援 CPU 推論。正式支援的執行環境為
`fastembed==0.8.0`，搭配專案所宣告的 CPU 版 `onnxruntime` 相依套件。
全新安裝不需要 GPU、CUDA、ROCm 或任何平台專用的加速器設定。

本版本未提供 GPU 加速的安裝選項，也不把 GPU 視為受支援的部署模式。
`fastembed` 與 `fastembed-gpu` 不能共存，`onnxruntime` 與
`onnxruntime-gpu` 也不能共存。若在正式支援的 CPU 環境中自行替換其中
一個套件，就會形成一套本專案尚未完成工程設計與測試的不同相依契約。

安裝 AIDEFEND MCP 1.3.0 時，請勿把專案宣告的 CPU 套件替換成 GPU
版本。未來若要正式支援 GPU，必須先建立獨立且無衝突的相依安裝路徑，
並完成安裝、模型、平台、降級行為與端到端測試，才能標示為受支援功能。

目前受支援的效能調校方式，請參閱
[效能最佳化摘要](../PERFORMANCE_OPTIMIZATION.md)中的 CPU 與 LanceDB 指引。
