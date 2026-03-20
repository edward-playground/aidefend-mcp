# Performance Optimization Summary

> **Note**: All optimizations in this document are **optional**. The service works well on CPU-only environments without any additional setup. GPU acceleration and indexing are recommended for production deployments requiring high throughput.

## Overview

This document summarizes the performance optimizations implemented to improve AIDEFEND MCP Service query speed from **3+ minutes** to **<1 minute** for complex queries.

**Date**: 2025-11-19

---

## Problem Analysis

### Original Performance

**User test**: "How can I defend against prompt injection attacks?"

- **Total time**: 3 minutes 15 seconds (195 seconds)
- **Tool execution time**: 2 minutes 15 seconds (135 seconds)
- **Tools called**: 6 tools (get_defenses_for_threat, query_aidefend × 2, comprehensive_search, get_technique_detail, get_secure_code_snippet)

### Identified Bottlenecks

1. **Comprehensive Search Tool**: 50-75 seconds (already parallelized ✅)
2. **Vector Search Latency**: 500-2000ms per query (CPU-only embedding)
3. **LanceDB Table Scan**: No index created (sequential scan)
4. **Multiple Tool Calls**: 6 serial tool invocations × 10s each = 60s overhead

---

## Optimizations Implemented

### 1. GPU Acceleration for Embeddings ⚡

**Change**: Modified `app/core.py` to use CUDA providers for FastEmbed

**Before**:
```python
self._model = TextEmbedding(model_name=resolved_model_name)
```

**After**:
```python
self._model = TextEmbedding(
    model_name=resolved_model_name,
    providers=["CUDAExecutionProvider", "CPUExecutionProvider"]  # GPU first, CPU fallback
)
```

**Expected Improvement**: 3-5x faster embedding generation
- CPU: 500-1000ms per query
- GPU: 100-300ms per query

**Requirements**:
- NVIDIA GPU
- CUDA Toolkit 12.x
- cuDNN 8.x
- `onnxruntime-gpu`

**Setup Guide**: [docs/GPU_OPTIMIZATION.md](GPU_OPTIMIZATION.md)

---

### 2. LanceDB Vector Index 🚀

**Change**: Created indexing script for production deployments

**Script**: [scripts/create_lancedb_index.py](../scripts/create_lancedb_index.py)

**Index Configuration**:
```python
table.create_index(
    metric="cosine",
    num_partitions=sqrt(row_count),
    num_sub_vectors=dimension // 16  # 48 for 768d vectors
)
```

**Expected Improvement**: 2-5x faster vector search
- Before index: 500-1000ms per search
- After index: 100-300ms per search

**Trade-offs**:
- One-time index creation: 5-10 minutes
- Slightly lower precision: 99%+ accuracy maintained
- Reduced memory usage for large databases

**Usage**:
```bash
# Run once after initial sync
python scripts/create_lancedb_index.py
```

---

### 3. Fixed Relevance Score Bug 🐛

**Issue**: `get_defenses_for_threat` returned all 0.00 relevance scores

**Root Cause**: Incorrect distance-to-score conversion
- LanceDB returns L2 distance (range: 0 to ∞)
- Old formula: `score = 1 - distance` (only works for range [0, 1])
- Result: All distances > 1.0 produced score = 0.00

**Fix**: Changed formula in `app/tools/defenses_for_threat.py`

**Before**:
```python
distance = doc.get('_distance', 0.5)
relevance_score = max(0.0, 1.0 - distance)  # ❌ Wrong for L2 distance
```

**After**:
```python
distance = doc.get('_distance', 1.0)
relevance_score = 1.0 / (1.0 + distance)  # ✅ Correct for L2 distance
```

**Formula Properties**:
- distance = 0.0 → score = 1.0 (perfect match)
- distance = 1.0 → score = 0.5 (moderate match)
- distance = 3.0 → score = 0.25
- distance = ∞ → score → 0.0

**Validation**: [tests/test_defenses_for_threat_fix.py](../tests/test_defenses_for_threat_fix.py)

---

## Performance Benchmarking

### Benchmark Tool

**Script**: [scripts/benchmark_search.py](../scripts/benchmark_search.py)

**Usage**:
```bash
python scripts/benchmark_search.py
```

**Tests**:
1. Single query benchmark
2. Multi-query benchmark (5 queries)
3. Comprehensive search benchmark

**Example Output**:
```
============================================================
BENCHMARK RESULTS
============================================================
Query: 'prompt injection attacks'
Top-K: 10
Results returned: 10

Total search time: 285.42 ms (0.2854 s)
Performance: ✅ EXCELLENT (< 500ms)

Top 3 results:
  1. AID-H-001: Input Validation (score: 0.1234)
  2. AID-D-003: Prompt Injection Detection (score: 0.2456)
  3. AID-M-002: Context Isolation (score: 0.3789)
============================================================
```

---

## Expected Performance Improvement

### Single Query

| Configuration | Time | Improvement |
|---------------|------|-------------|
| **Baseline (CPU, no index)** | 500-1000ms | - |
| CPU + Index | 250-500ms | 2x faster |
| GPU + No index | 200-400ms | 2.5x faster |
| **GPU + Index (optimal)** | **100-300ms** | **3-5x faster** |

### Comprehensive Search (5 parallel queries)

| Configuration | Time | Improvement |
|---------------|------|-------------|
| **Baseline** | 50-75s | - |
| Optimized (GPU + Index) | **10-20s** | **3-5x faster** |

### Full Tool Chain (Complex Query)

| Configuration | Total Time | Tool Time | Improvement |
|---------------|------------|-----------|-------------|
| **Baseline** | 3min 15s (195s) | 2min 15s (135s) | - |
| **Optimized** | **45-90s** | **30-60s** | **55-70% faster** |

---

## Production Deployment Checklist

### Quick Start (CPU Only - No Setup Required)

- [x] Service runs out-of-the-box with CPU
- [x] Reasonable performance for single queries (~500-1000ms)
- [x] Suitable for development and personal use

### Recommended Setup (CPU + Index)

- [ ] Initial sync completed
- [ ] Run `python scripts/create_lancedb_index.py`
- [ ] Restart service
- [ ] Expected: 2x performance improvement
- [ ] No additional dependencies needed

### Optimal Setup (GPU + Index)

**Prerequisites**:
- [ ] NVIDIA GPU available
- [ ] Windows 11 (or Linux/macOS with CUDA support)
- [ ] 2GB+ GPU memory

**Installation**:
- [ ] CUDA Toolkit 12.x installed
- [ ] cuDNN 8.x installed
- [ ] `pip install onnxruntime-gpu` (replaces onnxruntime)
- [ ] Index created (`python scripts/create_lancedb_index.py`)
- [ ] Service restarted

**Verification**:
- [ ] Logs show "✅ Embedding model loaded with GPU acceleration (CUDA)"
- [ ] `nvidia-smi` shows GPU utilization during queries
- [ ] Benchmark shows 3-5x improvement

**Troubleshooting**: See [docs/GPU_OPTIMIZATION.md](GPU_OPTIMIZATION.md)

---

## Architecture Notes

### Why Comprehensive Search Was Already Optimized

The `comprehensive_search` tool (lines 256-272 in `app/tools/comprehensive_search.py`) already uses parallel execution:

```python
# Create search tasks
search_tasks = []
for query_text in related_queries:
    query_request = QueryRequest(query_text=query_text, top_k=per_query_limit)
    search_tasks.append(query_engine.search(query_request))

# Execute all searches in parallel ✅
search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
```

**This was correctly implemented**, so no changes were needed. The bottleneck was:
1. Each individual search taking 10-15 seconds (slow embedding + no index)
2. Sequential tool calls by Claude (not controllable by our service)

By optimizing individual query speed (GPU + index), we speed up the entire chain.

---

## Monitoring & Metrics

### Log Indicators

**GPU Usage**:
```
INFO: ✅ Embedding model loaded with GPU acceleration (CUDA)
```

**CPU Fallback**:
```
WARNING: ⚠️  Embedding model loaded with CPU (provider: CPUExecutionProvider)
INFO: For faster performance, see docs/GPU_OPTIMIZATION.md
```

### Performance Metrics

**Check query time** in logs:
```
INFO: Query completed | results_returned=10 | top_score=0.1234
```

**Benchmark regularly**:
```bash
# Run monthly or after infrastructure changes
python scripts/benchmark_search.py
```

---

## Known Limitations

### What We Can Optimize

- ✅ Individual query speed (GPU, indexing)
- ✅ Parallel search execution (already implemented)
- ✅ Relevance score calculations (bug fixed)

### What We Cannot Control

- ❌ Claude's decision to call multiple tools sequentially
  - This is determined by Claude's reasoning process
  - We provide comprehensive tools to reduce multi-call needs
  - Example: `comprehensive_search` combines 5 searches in one call

- ❌ Network latency (for REST API mode)
  - Use local deployment to minimize
  - Consider localhost-only binding for best performance

- ❌ Initial sync time
  - Must download ~500 techniques from GitHub
  - Parse JavaScript files via Node.js subprocess
  - Generate embeddings for all content
  - Typical time: 2-5 minutes (one-time cost)

---

## Future Optimization Opportunities

### Priority 2 (Not Yet Implemented)

1. **Query Result Caching**
   - Cache recent query embeddings and results
   - Invalidate on sync
   - Expected: 10x faster for repeated queries

2. **Batch Embedding Generation**
   - Generate embeddings for multiple queries in one batch
   - Useful for comprehensive_search
   - Expected: 20-30% improvement

3. **Embedding Model Quantization**
   - Use INT8 quantized ONNX models
   - Trade-off: Slightly lower accuracy for 2x speed
   - Suitable for CPU deployments

### Priority 3 (Research)

1. **GPU Memory Pooling**
   - Reuse GPU memory allocations
   - Reduce allocation overhead

2. **Model Warming**
   - Pre-warm model on service startup
   - Eliminate first-query latency

---

## References

- **Benchmark Script**: [scripts/benchmark_search.py](../scripts/benchmark_search.py)
- **Index Creation**: [scripts/create_lancedb_index.py](../scripts/create_lancedb_index.py)
- **GPU Setup Guide**: [docs/GPU_OPTIMIZATION.md](GPU_OPTIMIZATION.md)
- **Relevance Fix Test**: [tests/test_defenses_for_threat_fix.py](../tests/test_defenses_for_threat_fix.py)

---

**Maintainer**: [Edward Lee](https://github.com/edward-playground)
**Last Updated**: 2025-11-19
