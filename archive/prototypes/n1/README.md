# Tesy

Tesy is an experimental local-inference project for **sparse/Mixture-of-Experts (MoE) language models on severely memory-constrained PCs**.

The long-term question is not "how many parameters can be advertised as loaded?". It is:

> How much useful exact model capacity can be made conversational under fixed VRAM, RAM, storage-bandwidth and latency budgets?

## Current research hypothesis

Existing work already covers expert offload, CPU/GPU expert scheduling, activation-aware caching, prefetching, and speculative decoding with MoE. Tesy therefore does **not** claim those ideas as novel.

The current candidate contribution is to investigate **joint speculative-residency scheduling** across an explicit NVMe -> RAM -> VRAM hierarchy. The optimization target is cold expert movement per exact committed token, rather than expert hit rate or speculative acceptance in isolation.

Novelty status: **NOT ESTABLISHED**.

## Reference hardware

Target host (must be re-verified before measurement):

- AMD Ryzen AI 9 HX 370, 12C/24T
- NVIDIA RTX 4060 Laptop, 8 GiB VRAM
- 32 GiB RAM
- NVMe
- Linux

## What exists in this branch

The first development slice provides:

- an adversarial research/novelty charter;
- a backend decision record;
- a strict machine-readable model candidate/lock file;
- host inspection and static planning utilities;
- a normalized MoE routing-trace schema;
- a deterministic two-tier RAM/VRAM LRU simulator with NVMe backing;
- speculative-window expert-union analysis;
- model verification helpers;
- synthetic unit tests;
- a concrete model installation guide.

It **does not yet** provide a Tesy-optimized model runtime, expert-prefetch backend, speculative decoder, or real-model performance result.

## Install for development

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e '.[dev]'
```

Then:

```bash
tesy doctor
tesy models list
tesy trace summarize path/to/routing.jsonl --windows 1,2,4,8
tesy simulate --trace path/to/routing.jsonl --ram-cache-gib 16 --vram-cache-gib 4
pytest -q
```

See `MODELOS_A_INSTALAR.md` before downloading any model.

## Claim policy

A simulator result is SIMULATED. A source-derived capacity calculation is ESTIMATED. A model run is only MEASURED when the exact host, model, binary, command and outputs were actually observed.

Negative results are retained. The project will pivot rather than weaken a gate after seeing a result.
