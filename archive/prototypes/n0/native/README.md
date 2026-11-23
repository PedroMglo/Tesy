# Actual CPU residency primitive — DEVELOPMENT_ONLY

This is an implemented read-only file-backed bounded cache with real `pread`,
immutable shared leases, LRU eviction, pinning, size/span checks, stable-FD
identity, poisoning after I/O/mutation and failure-atomic expert output.
It computes gate/up/down SwiGLU for compact native-endian F32 synthetic data.
It does NOT integrate with GGUF, llama.cpp, CUDA, quantized MoE routing or chat.
Do not report its result as an optimized LLM runtime or bitwise cross-backend proof.

Budget is payload bytes owned by the cache (LOADING reservation plus RESIDENT
and IN_USE), not total process RAM. Specs, vector/map metadata, caller activations
and compute scratch are separate. Active leases cannot be evicted; demand fails
without mutating cache entries when all reclaimable capacity is insufficient.
No async DMA or predictors are implemented here. File identity uses fstat; a
cryptographic manifest/admission boundary is required before real model data.
Parents are assumed user-owned, not concurrently adversarially renamed.

Source-read counters measure bytes returned by pread; warm page cache is possible.
The self-test is SYNTHETIC, uses a tiny generated file and never opens an LLM.
