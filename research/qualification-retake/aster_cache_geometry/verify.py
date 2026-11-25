"""Compile the pinned stock cache-restore branch with CPU fixture tokens and checkpoint reads."""

import argparse
import hashlib
import json
import os
import resource
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import two_turn_pair as pair  # noqa: E402

PIN = "e95426f16982054c379ca7bdc8186996dd22f0fe"
BLOBS = {
    "tools/server/server-context.cpp": "78c8ef149aedca2e8a873dcc1f9aebaa14f5861f",
    "tools/server/server-common.cpp": "311eb4f12fb4c5f1d3efd5e455997735fb3a59bf",
    "src/llama-kv-cache-iswa.cpp": "8ce8e0165f4da262a7fc6646ac3324cce38c6869",
    "common/common.h": "84abddc7609f25134a106f0c094ce7be3d95e4fa",
}
PROTO = "985bf10644e213241824e9a00b0606920ebbb34e0e910c289e2e47f917f32f12"


def h(data):
    return hashlib.sha256(data).hexdigest()


def demand(ok, reason):
    if not ok:
        raise ValueError(reason)


def blocks(context, common):
    def section(source, start, stop):
        return source[source.index(start) : source.index(stop, source.index(start))].rstrip()

    parts = {
        "PREFIX_GUARDS": section(
            context,
            "if (slot.task->params.cache_prompt && !slot.task->is_stateless())",
            "const auto n_cache_reuse",
        ),
        "SWA_MODE": section(context, "n_swa = params_base.swa_full", ";") + ";",
        "TEXT_LIMIT": section(
            context,
            "llama_pos pos_next = slot.prompt.tokens.pos_next(n_past);",
            "if (n_past > 0 && n_past <= slot.prompt.n_tokens())",
        ),
        "RESTORE": section(
            context,
            "if (pos_min >= pos_min_thold)",
            "\n                            }\n\n                            {",
        ),
        "LAST_LOGIT": section(
            context,
            "if (n_past == slot.task->n_tokens() && n_past > 0)",
            "slot.stats.n_prompt_cached",
        ),
        "TEXT_NEXT": section(
            common[common.index("llama_pos server_tokens::pos_next(") :],
            "if (n_tokens < 0)",
            "\n    }",
        ),
        "TEXT_SIZE": "return " + section(common, "std::min((size_t)max_pos, tokens.size());", "\n"),
        "TEXT_PREFIX": section(
            common[common.index("size_t server_tokens::get_common_prefix(") :],
            "const size_t max_idx",
            "\n    for (size_t i = 0; i < max_idx; ++i) {",
        ),
    }
    demand(parts["TEXT_PREFIX"].count("if (!has_mtmd)") == 1, "text-only LCP signature")
    parts["TEXT_PREFIX"] += '\n throw std::logic_error("text only");'
    return parts


def source(stock):
    def git(*args):
        return subprocess.check_output(["git", "-C", stock, *args], timeout=8)

    demand(git("rev-parse", "HEAD").decode().strip() == PIN, "unexpected stock pin")
    objects = {}
    for path, blob in BLOBS.items():
        demand(git("rev-parse", PIN + ":" + path).decode().strip() == blob, "unsealed stock source")
        objects[path] = git("cat-file", "blob", blob).decode()
    context, common, kv, options = objects.values()
    for text in [
        "if (slot.task->params.cache_prompt && !slot.task->is_stateless())",
        "n_past = slot.prompt.tokens.get_common_prefix(input_tokens);",
        "n_past = std::min(n_past, slot.task->n_tokens_shared);",
        "n_past = std::min(n_past, n_decision_first);",
        "n_past = std::min(n_past, slot.alora_invocation_start - 1);",
        "if (can_cache_reuse && n_cache_reuse > 0)",
        "cur.update_pos(slot.prompt.n_tokens() - n_tokens_cur, pos_min, pos_max);",
        "if (cur.pos_max > pos_next || cur.n_tokens > n_prefix)",
        "static const int checkpoint_offsets[] = {4 + n_ubatch, 4};",
        "slot.stats.n_prompt_cached    = n_past;",
        "slot.mem.seq_rm(slot.id, p0, -1);",
        "if (f_keep < 0.5f)",
        "if (!ret->prompt_load(*prompt_cache, task.tokens))",
    ]:
        demand(text in context, "missing server guard")
    demand(
        context.count("create_checkpoint(") == 2
        and "create_checkpoint(slot, n_tokens_cur, pos_min, pos_max);" in context,
        "new checkpoint producer; proof needs revision",
    )
    demand(
        "n_cache_reuse       = 0" in options
        and "slot_prompt_similarity = 0.1f" in options
        and "GGML_PAD(std::min(size_base, hparams.n_swa*(unified ? n_seq_max : 1) + n_ubatch), 256)"
        in kv
        and "size_swa = size_base;" in kv,
        "geometry or defaults changed",
    )
    data = (HERE / "fixture.cpp.in").read_text()
    for name, txt in blocks(context, common).items():
        demand(data.count("@" + name + "@") == 1, "fixture placeholder")
        data = data.replace("@" + name + "@", txt)
    return data


def probe_inputs(history):
    manifest, *_ = pair.prepare(history)
    demand(
        pair.digest(manifest) == "0a96782a6be10028f4d91bbbd5d0f1efafe7327e6364281645fe0e7db5795b9f",
        "input manifest",
    )
    raw = (
        history
        / pair.historical.ROOT_NAME
        / "raw"
        / (pair.historical.RUN_ID + ".tokenization.json")
    )
    ids = pair.read(raw, manifest["tokenizations_sha256"])
    first, second = (ids[k] for k in pair.IDS)
    demand(len(first) == 121 and len(second) == 435 and first == second[:121], "unexpected prompts")
    # Request a deliberately different next ID from the same historical input.
    # Any one sampled token can follow this marker without altering the fixed LCP.
    marker = next(i for i in second if i != second[122])
    primer = [*second[:122], marker]
    demand(primer[:122] == second[:122] and primer[122] != second[122], "probe prefix boundary")
    return primer, second


def bounded():
    resource.setrlimit(resource.RLIMIT_AS, (256 << 20, 256 << 20))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8 << 20, 8 << 20))


def test(a):
    demand(h((HERE / "protocol.md").read_bytes()) == PROTO, "source protocol changed")
    start = time.monotonic()
    out = a.new_output_dir
    out.mkdir(mode=0o700)
    receipt = {
        "status": "FAIL_PRESERVED",
        "model_processes": 0,
        "gpu_work": 0,
        "protocol_sha256": PROTO,
    }
    try:
        data = source(a.stock)
        primer, second = probe_inputs(a.historical_results)
        work = out / "private"
        work.mkdir()
        cpp, exe = work / "case.cpp", work / "case"
        cpp.write_text(data)
        for cmd in [
            [
                "/usr/bin/c++",
                "-std=c++17",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-Wno-unused-variable",
                f"-ffile-prefix-map={work}=/tesy-aster-geometry",
                str(cpp),
                "-o",
                str(exe),
            ],
            [str(exe)],
        ]:
            p = subprocess.run(
                cmd,
                capture_output=True,
                timeout=45,
                preexec_fn=bounded,
                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
            )
            (work / ("compile.log" if cmd[0] == "/usr/bin/c++" else "fixture.log")).write_bytes(
                p.stdout + p.stderr
            )
            demand(p.returncode == 0, "compiler/fixture failed: " + p.stderr.decode()[-600:])
        got = p.stdout.decode().strip()
        demand(
            got == "106384 source-branch comparisons; full=122 compact=0 no-checkpoint",
            "fixture result",
        )
        receipt.update(
            compiled_source_sha256=h(data.encode()),
            executable_sha256=h(exe.read_bytes()),
            fixture_source_sha256=h((HERE / "fixture.cpp.in").read_bytes()),
            compiler=h(Path("/usr/bin/c++").read_bytes()),
            fixture_stdout=got,
        )
        receipt.update(
            status="PASS_SOURCE_CACHE_GEOMETRY",
            stock_pin=PIN,
            stock_blob=BLOBS,
            natural_compact_split_122="IMPOSSIBLE_UNDER_TWO_REQUEST_CONTRACT",
            full_split="CONDITIONALLY_ADMISSIBLE",
            primer_ids=len(primer),
            primer_sha256=pair.digest(primer),
            second_ids=len(second),
            second_sha256=pair.digest(second),
            live_122_313="NOT_RUN",
            window=128,
            compact_cells=256,
            full_cells=8192,
            incremental_kv_bytes_estimated=(8192 - 256) * 18 * 8 * 64 * 2 * 2,
        )
    except (OSError, ValueError, RuntimeError, StopIteration, subprocess.SubprocessError) as exc:
        receipt["error"] = str(exc)
    receipt["private_output_bytes"] = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    receipt["verifier_sha256"] = h(Path(__file__).read_bytes())
    receipt["wall_s"] = round(time.monotonic() - start, 4)
    receipt["max_subprocess_rss_kib"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    if (
        receipt["wall_s"] > 60
        or receipt["max_subprocess_rss_kib"] > 256 * 1024
        or receipt["private_output_bytes"] > 8 << 20
    ):
        receipt["status"] = "FAIL_BUDGET"
    with (out / "receipt.json").open("x") as f:
        json.dump(receipt, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("stock", "historical-results", "new-output-dir"):
        parser.add_argument("--" + arg, required=True, type=Path)
    os.umask(0o077)

    def timeout(signum, frame):
        raise TimeoutError("fixture deadline")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(60)
    result = test(parser.parse_args())
    print(result["status"], result.get("error", ""))
    raise SystemExit(int(result["status"] != "PASS_SOURCE_CACHE_GEOMETRY"))
