"""Qualify the ELF capture with private synthetic rows and a mock provider.

For a separate stock120b run, LD_PRELOAD the qualified observer.so and set TESY_F32_DIR to an
exclusive empty mode-0700 directory, TESY_F32_PROFILE=stock120b and TESY_F32_PROVIDER_SHA256
to the prequalified libllama digest. Only after READY, atomically publish ARM with the exact
ARM_BYTES defined here, before submitting one frozen 16-ID request. Leave ARM until normal
server exit. Capture validation also requires that the parent authenticated the actual GGUF,
whole prompt, request options/HTTP ID, server geometry, namespace, PID and process cleanup.
"""

import argparse
import datetime
import hashlib
import json
import os
import selectors
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WIDTH = 201088
ARM_BYTES = b"tesy-first-prompt16-v1\n"
LABEL = "PASS_SYNTHETIC_SERVER_LOGIT_OBSERVER"
TOOL = "/usr/bin/g++"
FLAGS = ["-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-fPIC", "-fno-optimize-sibling-calls"]

PROVIDER = r"""
#include <array>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <sys/mman.h>
struct llama_context {};
struct llama_vocab {};
struct llama_model {};
static constexpr int k = 201088;
static std::array<float,k*2> data;
static llama_context ctx;
static llama_vocab vocab;
static llama_model model;
static float *guard = nullptr;
static bool is(const char *name) { return !strcmp(getenv("CASE"),name); }
extern "C" void init_data() {
    guard = static_cast<float *>(mmap(nullptr,4096,PROT_NONE,MAP_PRIVATE | MAP_ANONYMOUS,-1,0));
    if (guard == MAP_FAILED) std::abort();
    for (size_t i=0; i<data.size(); ++i) data[i]=static_cast<int>(i%97)-48;
    data[0]=-0.0f; data[4567]=100.0f;
    if (is("same_argmax")) data[123]=0.125f;
    if (is("nonfinite")) data[42]=INFINITY;
}
extern "C" llama_context *fixture_ctx() { return &ctx; }
extern "C" float *fixture_expected(int idx) {
    if (is("null")) return nullptr;
    if (is("short_vocab") || is("wrong_model")) return guard;
    if (is("two_rows") && idx==-1) return data.data()+k;
    return data.data();
}
extern "C" float *llama_get_logits_ith(llama_context *,int idx) {
    if (errno!=EDOM && idx>=0) std::abort();
    errno=EILSEQ;
    return fixture_expected(idx);
}
extern "C" float *llama_get_logits(llama_context *) {
    if (is("not_base")) return data.data()+1;
    return data.data();
}
extern "C" const llama_model *llama_get_model(const llama_context *) { return &model; }
extern "C" const llama_vocab *llama_model_get_vocab(const llama_model *) { return &vocab; }
extern "C" int32_t llama_vocab_n_tokens(const llama_vocab *) { return is("short_vocab") ? 1 : k; }
extern "C" int32_t llama_model_n_embd(const llama_model *) { return is("wrong_model") ? 8 : 2880; }
extern "C" int32_t llama_model_n_layer(const llama_model *) { return 36; }
extern "C" int32_t llama_model_meta_val_str(const llama_model *,const char *key,char *p,size_t n) {
    if (strcmp(key,"general.architecture") || n<8) return -1;
    memcpy(p,"gpt-oss",8); return 7;
}
extern "C" float *llama_get_sampled_probs_ith(llama_context *,int) {
    return is("sampled_probs") ? data.data() : nullptr;
}
extern "C" float *llama_get_sampled_logits_ith(llama_context *,int i) {
    return is("sampled_logits") || (is("last_sampled") && i==-1) ? data.data() : nullptr;
}
extern "C" int32_t llama_get_sampled_token_ith(llama_context *,int) {
    return is("sampled_token") ? 7 : -1;
}
// Non-null candidate IDs can exist independently of a backend sample.
extern "C" int32_t *llama_get_sampled_candidates_ith(llama_context *,int) {
    static int32_t diagnostic_candidate=7; return &diagnostic_candidate;
}
"""

CALLER = r"""
#include <cerrno>
#include <cstdlib>
struct common_sampler;
struct llama_context;
extern "C" float *llama_get_logits_ith(llama_context *,int);
extern "C" float *fixture_expected(int);
__attribute__((noinline))
int common_sampler_sample(common_sampler *,llama_context *ctx,int idx,bool) {
    auto *expected = fixture_expected(idx);
    errno=EDOM;
    auto *result=llama_get_logits_ith(ctx,idx);
    return result==expected && errno==EILSEQ ? 0 : 1;
}
extern "C" __attribute__((noinline)) int unrelated(llama_context *ctx,int idx) {
    auto *expected = fixture_expected(idx);
    errno=EDOM;
    auto *result=llama_get_logits_ith(ctx,idx);
    return result==expected && errno==EILSEQ ? 0 : 1;
}
"""

DRIVER = r"""
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>
#include <unistd.h>
struct common_sampler; struct llama_context;
int common_sampler_sample(common_sampler *,llama_context *,int,bool);
extern "C" int unrelated(llama_context *,int);
extern "C" void init_data();
extern "C" llama_context *fixture_ctx();
int main() {
    const char *mode=getenv("CASE");
    init_data();
    auto *ctx=fixture_ctx();
    auto sample=[&](int i) { return common_sampler_sample(nullptr,ctx,i,false); };
    if (sample(3) || sample(5)) return 21;
    puts("READY"); fflush(stdout);
    if (getchar()!='G') return 22;
    int rc=0;
    if (!strcmp(mode,"wrong_caller")) rc=unrelated(ctx,15);
    else if (!strcmp(mode,"concurrent")) {
        int other=0; std::thread t([&]{other=sample(15);}); rc=sample(15); t.join(); rc|=other;
    } else if (strcmp(mode,"missing")) rc=sample(!strcmp(mode,"wrong_index") ? 14 : 15);
    if (!strcmp(mode,"duplicate")) rc|=sample(15);
    if (!strcmp(mode,"lost_arm")) {
        if (unlink("capture/ARM")) return 23;
    }
    if (!strcmp(mode,"crash")) _exit(rc);
    return rc;
}
"""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(ok, label):
    if not ok:
        raise ValueError(label)


def run_build(private):
    for name, source in [("provider", PROVIDER), ("caller", CALLER), ("driver", DRIVER)]:
        (private / (name + ".cpp")).write_text(source)
    cmds = [
        [
            str(HERE / "capture.cpp"),
            "-shared",
            "-fvisibility=hidden",
            "-pthread",
            "-lcrypto",
            "-ldl",
            "-o",
            "observer.so",
        ],
        [
            "provider.cpp",
            "-shared",
            "-Wl,-soname,libfixture-provider.so",
            "-o",
            "libfixture-provider.so",
        ],
        [
            "caller.cpp",
            "-shared",
            "-L.",
            "-lfixture-provider",
            "-Wl,-rpath,$ORIGIN",
            "-Wl,-soname,libfixture-caller.so",
            "-o",
            "libfixture-caller.so",
        ],
        [
            "driver.cpp",
            "-L.",
            "-lfixture-caller",
            "-lfixture-provider",
            "-Wl,-rpath,$ORIGIN",
            "-pthread",
            "-o",
            "driver",
        ],
    ]
    for i, args in enumerate(cmds):
        with (private / f"compile-{i}.log").open("xb") as log:
            subprocess.run(
                [TOOL, *FLAGS, *args],
                cwd=private,
                timeout=30,
                check=True,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
    return [
        Path(name)
        for name in ("observer.so", "libfixture-provider.so", "libfixture-caller.so", "driver")
    ]


def arm(path):
    pending = path / "ARM.new"
    with pending.open("xb") as f:
        f.write(ARM_BYTES)
        f.flush()
        os.fsync(f.fileno())
    os.link(pending, path / "ARM")
    pending.unlink()


def expected_row(changed=False):
    out = bytearray(4 * WIDTH)
    for i in range(WIDTH):
        struct.pack_into("<f", out, 4 * i, float(i % 97 - 48))
    struct.pack_into("<f", out, 0, -0.0)
    struct.pack_into("<f", out, 4 * 4567, 100.0)
    if changed:
        struct.pack_into("<f", out, 4 * 123, 0.125)
    return bytes(out)


def run_case(private, case, expected):
    root = private / case
    root.mkdir(mode=0o700)
    capture_dir = root / "capture"
    capture_dir.mkdir(mode=0o700)
    observer = private / "observer.so"
    caller = private / "libfixture-caller.so"
    provider = private / "libfixture-provider.so"
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("LD_", "TESY_F32_"))}
    env = dict(clean, LD_PRELOAD=str(observer), CASE=case)
    if case != "off":
        env.update(
            TESY_F32_DIR=str(capture_dir),
            TESY_F32_PROFILE="mock",
            TESY_F32_PROVIDER_SHA256=sha(provider.read_bytes()),
            TESY_F32_CALLER_SHA256=sha(caller.read_bytes()),
        )
    if case == "wrong_provider":
        env["TESY_F32_PROVIDER_SHA256"] = "0" * 64
    if case == "stock_rejects_mock":
        env["TESY_F32_PROFILE"] = "stock120b"
    if case == "early_arm":
        arm(capture_dir)
    with (root / "stderr").open("xb") as log:
        proc = subprocess.Popen(
            [str(private / "driver")],
            env=env,
            cwd=root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=log,
        )
        try:
            with selectors.DefaultSelector() as poll:
                poll.register(proc.stdout, selectors.EVENT_READ)
                require(poll.select(10), "mock_ready_timeout")
                line = proc.stdout.readline()
            if case in {"early_arm", "stock_rejects_mock"}:
                require(
                    line == b""
                    and proc.wait(10) == 125
                    and not (capture_dir / "capture.json").exists(),
                    "startup_guard",
                )
                return {"case": case, "status": "REJECTED_BEFORE_MAIN"}
            require(line == b"READY\n", "mock_ready")
            require(not list(capture_dir.iterdir()), "capture_before_arming")
            if case not in {"off", "no_arm"}:
                arm(capture_dir)
            if case == "collision":
                (capture_dir / "row.f32").write_bytes(b"guard")
            proc.stdin.write(b"G")
            proc.stdin.flush()
            require(proc.wait(10) == 0, "mock_forwarding_pointer_or_errno")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            proc.stdin.close()
            proc.stdout.close()
    end = capture_dir / "capture.json"
    if case in {"off", "crash"}:
        require(not end.exists(), "missing_terminal_fence")
        require((capture_dir / "row.f32").exists() is (case == "crash"), "disabled_or_crashed_data")
        return {"case": case, "status": "OFF" if case == "off" else "INCOMPLETE_REJECTED"}
    data = json.loads(end.read_bytes())
    require(data["profile"] == "mock", "profile")
    if case == "no_arm":
        require(data["prearm_calls"] == 3, "all_unarmed_calls")
    else:
        require(data["prearm_calls"] == 2, "startup_forward_count")
    if expected == "PASS":
        row = (capture_dir / "row.f32").read_bytes()
        require(
            row == expected_row(case == "same_argmax")
            and sha(row) == data["row_sha256"]
            and data["status"] == "PASS"
            and data["reason"] == ""
            and data["armed_calls"] == 1
            and data["n_vocab"] == WIDTH
            and data["row_index"] == 15
            and data["row_bytes"] == 4 * WIDTH
            and data["argmax"] == 4567
            and data["caller_sha256"] == env["TESY_F32_CALLER_SHA256"]
            and data["provider_sha256"] == env["TESY_F32_PROVIDER_SHA256"]
            and not list(capture_dir.glob("*.part")),
            "synthetic_gold",
        )
        return {"case": case, "status": "PASS", "row_sha256": sha(row), "argmax": data["argmax"]}
    require(data["status"] == "FAIL" and data["reason"] == expected, "wrong_negative_outcome")
    if case in {"duplicate", "concurrent"}:
        require(data["armed_calls"] == 2, "duplicate_count")
    elif case == "lost_arm":
        require((capture_dir / "row.f32").is_file(), "incomplete_handoff_not_preserved")
    elif case == "collision":
        require((capture_dir / "row.f32").read_bytes() == b"guard", "overwritten_output")
    else:
        require(not (capture_dir / "row.f32").exists(), "output_on_failed_validation")
    return {"case": case, "status": "EXPECTED_FAIL", "reason": data["reason"]}


CASES = {
    "off": None,
    "normal": "PASS",
    "same_argmax": "PASS",
    "short_vocab": "vocab_shape",
    "wrong_model": "model_shape",
    "wrong_provider": "image_digest",
    "wrong_index": "row_or_index",
    "wrong_caller": "wrong_caller",
    "null": "row_or_index",
    "two_rows": "multiple_rows_or_nonraw",
    "not_base": "multiple_rows_or_nonraw",
    "sampled_probs": "backend_sampled",
    "sampled_logits": "backend_sampled",
    "sampled_token": "backend_sampled",
    "last_sampled": "backend_sampled",
    "nonfinite": "nonfinite",
    "duplicate": "invalid_arm_or_duplicate",
    "concurrent": "invalid_arm_or_duplicate",
    "lost_arm": "invalid_seal_arm",
    "missing": "missing_complete_capture",
    "no_arm": "missing_complete_capture",
    "collision": "publish_collision",
    "early_arm": None,
    "crash": None,
    "stock_rejects_mock": None,
}


def exercise(private):
    binaries = run_build(private)
    cases = [run_case(private, case, outcome) for case, outcome in CASES.items()]
    by_name = {row["case"]: row for row in cases}
    require(
        by_name["normal"]["argmax"] == by_name["same_argmax"]["argmax"]
        and by_name["normal"]["row_sha256"] != by_name["same_argmax"]["row_sha256"],
        "same_argmax_different_bits",
    )
    return {
        "status": LABEL,
        "cases": cases,
        "observer_sha256": sha((private / "observer.so").read_bytes()),
        "binary_sha256": {p.name: sha((private / p).read_bytes()) for p in binaries},
        "compiler_sha256": sha(Path(TOOL).read_bytes()),
        "flags": FLAGS,
    }


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--new-output-dir", type=Path, required=True)
    cli.add_argument("--new-private", type=Path)
    args = cli.parse_args()
    out = args.new_output_dir.resolve()
    private = (args.new_private or out.with_name(out.name + ".private")).resolve()
    out.mkdir(mode=0o700, exist_ok=False)
    receipt = {
        "model_forwards": 0,
        "gpu_used": False,
        "sources_sha256": {
            n: sha((HERE / n).read_bytes())
            for n in ["capture.cpp", "fixture.py", "test_fixture.py"]
        },
        "program_sha256": sha(Path(__file__).read_bytes()),
    }
    try:
        revision = [
            "git",
            "--no-optional-locks",
            "-c",
            "core.preloadIndex=false",
            "-c",
            "index.threads=1",
            "-C",
            str(HERE),
        ]
        require(
            not subprocess.check_output(revision + ["status", "--porcelain"]), "unclean_checkout"
        )
        receipt["measurement_commit"] = subprocess.check_output(
            revision + ["rev-parse", "HEAD"], text=True
        ).strip()
        receipt["measurement_tree"] = subprocess.check_output(
            revision + ["rev-parse", "HEAD^{tree}"], text=True
        ).strip()
        private.mkdir(mode=0o700, exist_ok=False)
        receipt.update(exercise(private))
        receipt["private_bytes"] = sum(p.stat().st_size for p in private.rglob("*") if p.is_file())
        require(receipt["private_bytes"] < 24 * 1024**2 - 65536, "raw_byte_budget")
    except Exception as e:
        receipt.update(status="FAIL", reason=f"{type(e).__name__}: {e}")
    receipt["finished_utc"] = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
    with (out / "receipt.json").open("x") as f:
        json.dump(receipt, f, indent=2, sort_keys=True)
        f.write("\n")
    print(receipt["status"])
    return int(receipt["status"] != LABEL)


if __name__ == "__main__":
    sys.exit(main())
