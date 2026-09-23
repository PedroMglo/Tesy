# Tesy

Research and engineering for **natural-routing MoE inference on a constrained
Linux laptop**: Ryzen AI 9 HX 370, RTX 4060 Laptop 8 GiB, 32 GiB RAM, NVMe.

**Status: DEVELOPMENT_ONLY. Scientific novelty and end-to-end speedup are NOT
established. This is not yet a production dynamic MoE inference runtime.**

The initial implementation contains a real file-backed native F32 expert cache,
strict trace replay, bounded GGUF inspection, an explicit transport planner and
an opt-in supervised **stock llama.cpp** chat handoff. The native cache is not
yet wired into llama.cpp's quantized expert path. Traces for replay must currently
be supplied in the documented format; live routing capture is the next gate.

## Install and test without any model or GPU

Run from the checkout root (configuration defaults are relative to the root):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install --no-build-isolation -e .
bash scripts/test.sh
```

Only the development dependency installation needs a package connection. The
core package has no external Python runtime dependencies. Linux, CMake >=3.16
and a C++17 compiler are required for native tests. Nothing installs a driver,
modifies swap, changes mounts, downloads models or starts a server.

```bash
tesy doctor
tesy simulate --trace examples/routing.synthetic.json \
  --profile examples/synthetic-profile.json --policy lru
tesy simulate --trace examples/routing.synthetic.json \
  --profile examples/synthetic-profile.json --policy transition
tesy union --trace examples/routing.synthetic.json --k 3
tesy plan --contract examples/roofline.synthetic.json
```

`--output /existing/trusted/directory/new-result.json` publishes a result with
no replacement and readback. An existing path, including a dangling symlink,
is rejected. Without `--output`, commands emit JSON to stdout.

## One model to install first

Read **[MODELOS_A_INSTALAR.md](MODELOS_A_INSTALAR.md)**. The locked first candidate
is Qwen3-30B-A3B-Instruct-2507 Q4_K_M from Unsloth, one 18,556,686,752-byte GGUF.
This is a publisher-identified artefact, **not a model tested on your laptop**.

```bash
tesy models download-plan --id qwen3-30b-a3b-2507-q4km "$HOME/.local/share/tesy/models"
```

This prints the exact `hf download` argument list without downloading anything.
The guide contains the manual download and verification commands.

After the user builds the pinned external backend and installs/verifies the model:

```bash
bash scripts/build_stock.sh
MODEL="$HOME/.local/share/tesy/models/Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf"
tesy models inspect "$MODEL"
tesy models verify --id qwen3-30b-a3b-2507-q4km "$MODEL"
tesy chat --model "$MODEL" --llama-cli third_party/llama.cpp/build-tesy/bin/llama-cli
# Above prints a plan only. This next command explicitly launches stock inference:
tesy chat --model "$MODEL" --llama-cli third_party/llama.cpp/build-tesy/bin/llama-cli --execute
```

The launcher checks file identity, source version reported by the binary and
live memory/GPU conditions. It retains a model FD, removes implicit model/network
configuration variables, disables speculation/op-offload, and stops its child
process group on guard failure/cancel/timeout. Default wall limit: 600 seconds,
maximum: 1800 seconds. Missing resource data fails closed. CPU-temperature and
power telemetry are not yet implemented; this is **not a formal benchmark**.
Sampling guards cannot guarantee prevention of every transient OOM.

The first stock profile puts expert weights/compute on CPU and up to 48 other
layers on GPU. `--cpu-only` is an explicit alternative. Neither is an optimized
Tesy cache mode. External stock/CUDA build and real-model launch are **NOT_RUN**
in this development container. No observed tokens/s can be given yet.

## Research boundary

Known prior art includes MoE-Infinity, DALI, MoE-SpeQ, AcceptMoE and SeqMoE.
See [N0 decision](research/n0/DECISION.md) for dated primary sources, overlaps,
screening depth and uncertainties. Merely combining caching and speculation
is not a novelty claim. Natural target routing remains authoritative.

A positive target-only union analysis is not proof of speculative acceptance:
rejected drafts can activate additional experts. Hit rate alone is not useful
progress: the synthetic transition policy increases hits while also transferring
more bytes. See the [development report](research/n0/VALIDATION.md).

## Documentation

- [Implementation status](IMPLEMENTATION_STATUS.md): what exists and what does not.
- [Architecture and contracts](docs/ARCHITECTURE.md): byte semantics and trust boundaries.
- [Model installation](MODELOS_A_INSTALAR.md): one exact initial artefact, no blind bulk download.
- [Next engineering handoff](docs/HANDOFF.md): native tracing/integration gate.

No historical MOSAIC source, output, gate or runtime is imported. No licence for
redistribution of Tesy's own code has been selected by the owner in this phase;
do not assume an open-source licence. Model/backend licences are separate.
