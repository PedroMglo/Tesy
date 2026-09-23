# Executed commands and output roots

The exact runner arguments and relevant environment for the successful diagnostic campaign were:

```bash
export PATH="/home/pmglo/Projects/Tesy/.venv/bin:/usr/local/cuda/bin:$PATH"
export CC=/usr/bin/gcc-15 CXX=/usr/bin/g++-15
export CUDAHOSTCXX=/usr/bin/g++-15 CUDACXX=/usr/local/cuda/bin/nvcc
export TESY_BUILD_JOBS=4

bash scripts/run_reference_bringup.sh \
  /home/pmglo/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf \
  results/bringup-20260923T205424Z
```

The runner invokes the pinned backend/tracer/gguf-py bootstrap scripts, stock smoke, paired trace runner, and GGUF inventory. The stock and tracer runner command files remain in the untracked output root; their SHA-256 values are in `manifest.json`. The diagnostic tracer used `TESY_TRACE_NGL=0`, `--ctx 4096`, `--n-predict 16` and `--raw-prompt`. Stock smoke used `--ctx-size 4096`, `--n-predict 16`, `--gpu-layers auto`, `--fit on`, `--fit-target 1024`, `--temperature 0`, `--top-k 1`, `--seed 42`, `--no-warmup`, `--simple-io`, `--no-display-prompt` and `--single-turn`.

After the pipeline passed, the prospectively specified trace-derived analysis was:

```bash
python3 -m tesy trace simulate-native \
  results/bringup-20260923T205424Z/trace-exactness/routing.jsonl \
  --inventory results/bringup-20260923T205424Z/expert-inventory.json \
  --ram-cache-gib 16 --vram-cache-gib 4 --min-graph-seq 1 \
  > results/bringup-20260923T205424Z/byte-weighted-simulation.json
```

Prior output roots are preserved as `results/bringup-20260923T203354Z` (FAIL_NATIVE_BUILD) and `results/bringup-20260923T204412Z` (ABORTED_CONCURRENT). No result root was reused or deleted.
