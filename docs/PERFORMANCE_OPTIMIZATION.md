# Performance Optimization Summary

> AIDEFEND MCP 1.3.0 supports CPU inference only. Its supported embedding
> runtime is `fastembed==0.8.0` with the project's declared CPU
> `onnxruntime` dependency. Performance varies with hardware, operating system,
> model cache state, Framework data, and query shape, so this project does not
> publish a universal latency or speedup expectation.

## Supported performance path

The service uses a local FastEmbed/ONNX model and a local LanceDB database. A
standard installation works without accelerator hardware or additional
platform packages. For production tuning:

1. Complete the initial Framework sync and model download.
2. Measure representative queries on the target host.
3. Optionally create a LanceDB vector index for a sufficiently large database.
4. Measure the same workload again and keep the index only when it improves the
   deployment's actual workload without unacceptable retrieval trade-offs.

GPU acceleration is not a supported installation or deployment mode in 1.3.0.
See [GPU Acceleration Status](advanced/GPU_ACCELERATION.md) for the dependency
boundary and future support requirements.

## LanceDB vector index

The repository includes
[`scripts/create_lancedb_index.py`](../scripts/create_lancedb_index.py), which
creates an IVF-PQ index over the synchronized `aidefend` table. It derives the
partition and sub-vector settings from the current row count and configured
embedding dimension.

Run the maintenance command only after the initial sync has completed and only
while no REST server, MCP server, resync, benchmark, or other maintenance
process owns the same `DATA_PATH`:

```bash
python scripts/create_lancedb_index.py
```

Restart the service after successful index creation. Index construction takes
additional time and storage, and its benefit and retrieval behavior depend on
the local corpus and workload. Validate both result quality and measured query
time in the target environment.

## Parallel comprehensive search

The `comprehensive_search` tool executes its related vector searches
concurrently and then deduplicates their results. This reduces avoidable
serialization inside that tool, but it does not control whether an MCP client
chooses to call several separate tools sequentially.

## Relevance-score correctness

Search result distance is converted to the public relevance score with:

```python
relevance_score = 1.0 / (1.0 + distance)
```

This preserves a bounded, monotonic score for non-negative distances instead
of truncating every distance above one to zero. Regression coverage is in
[`tests/test_defenses_for_threat_fix.py`](../tests/test_defenses_for_threat_fix.py).

## Benchmarking

Use the repository benchmark script to measure the installed environment:

```bash
python scripts/benchmark_search.py
```

The script exercises single-query, multi-query, and comprehensive-search
workloads and reports measurements from the machine on which it runs. For a
meaningful comparison:

- use the same Framework revision, model, queries, and `top_k` values;
- allow the model to warm up before recording results;
- compare repeated runs rather than one isolated observation;
- record result quality as well as elapsed time; and
- run the benchmark with exclusive ownership of its configured `DATA_PATH`.

Treat the script's output as deployment-specific evidence, not as a performance
guarantee for other hardware or environments.

## Production checklist

- [ ] Install the declared 1.3.0 runtime dependencies without substituting GPU
      variants.
- [ ] Complete a fresh Framework sync and confirm the service is ready.
- [ ] Keep `API_WORKERS=1` and give each process an independent `DATA_PATH`.
- [ ] Benchmark representative queries on the deployment host.
- [ ] If appropriate, create the LanceDB index while the data directory is not
      owned by another process.
- [ ] Restart the service, rerun the same benchmark, and compare result quality.
- [ ] Monitor CPU, memory, disk, and query behavior under realistic load.

## Known boundaries

- Initial setup includes the Framework sync, model download, and embedding
  generation; duration depends on the host and network.
- REST latency includes the caller's network and HTTP overhead.
- Client-side decisions to make several tool calls are outside the service's
  execution scheduler.
- GPU, CUDA, ROCm, CoreML, and other accelerator paths are not supported or
  release-tested in 1.3.0.

## Future optimization work

Potential work such as query-result caching, batch query embeddings, model
warming, and accelerator-specific distributions must be implemented and tested
before it is described as available. No performance estimate is promised for
unimplemented work.

## References

- [Benchmark script](../scripts/benchmark_search.py)
- [Index creation script](../scripts/create_lancedb_index.py)
- [GPU acceleration status](advanced/GPU_ACCELERATION.md)
- [Configuration](CONFIGURATION.md)

---

**Maintainer**: [Edward Lee](https://github.com/edward-playground)

**Last updated**: 2026-08-06
