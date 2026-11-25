"""Attribute the tiny fixture's matmuls to actual kernel and backend calls, in process."""

import argparse
import functools
import importlib.util
import resource
import sys
from pathlib import Path

import runner as guard

HERE = Path(__file__).resolve().parent
GUARD_SHA = "385556de0929051fb526c8f98012c461b318172844d9ec5c8f16fedc4d2b7ff4"
PROTOCOL_SHA = "4629add191f8528d480431c53599a5354a0e14684e282ccba3f4fda403bd3c22"
R1_RECEIPT = "05791035d67b7597f10c6b2d8189b629f65f283183d56681e4873cf8196c07aa"
R1_LOGITS = "aabc5c6e701c0df890d1fa21c9b590dcd4bf8a29f56390c1beb3f169848d1290"
R1_STDOUT = "e67fa5dea374653b9fd4d7ba986a9886910e6a16fad5a6b076209b64f501b55c"

# Single-thread llama_decode runs. Only the requested MUL_MAT can be awaiting dispatch
# at a given time: the scheduler stops its graph view at the first subscribed tensor.
HOOK = r"""
struct ggml_compute_params;
static struct {
    ggml_tensor *asked;
    int pass, asks, kernels, matches, bad, dispatch, bad_backend, buf_cpu, buf_other;
    bool decoding, in_cpu_dispatch, returned;
} obs;
static void provider(const char *role, const void *fn) {
    Dl_info info{};
    if (!fn || !dladdr(fn, &info) || !info.dli_fname) std::abort();
    printf("PROVIDER %s %s\n", role, info.dli_fname);
}
extern "C" void ggml_compute_forward_mul_mat(const ggml_compute_params *params, ggml_tensor *dst) {
    using Fn = decltype(&ggml_compute_forward_mul_mat);
    static const Fn next = (Fn)dlsym(RTLD_NEXT, "ggml_compute_forward_mul_mat");
    if (!next) std::abort();
    next(params, dst);
    if (!obs.decoding) return;
    if (obs.kernels++ == 0) provider("kernel", (const void *)next);
    if (!obs.in_cpu_dispatch || obs.asked != dst || obs.returned) ++obs.bad;
    else obs.returned = true;
}
extern "C" enum ggml_status ggml_backend_graph_compute_async(ggml_backend_t backend,
                                                             ggml_cgraph *graph) {
    using Fn = decltype(&ggml_backend_graph_compute_async);
    static const Fn next = (Fn)dlsym(RTLD_NEXT, "ggml_backend_graph_compute_async");
    if (!next) std::abort();
    if (!obs.decoding) return next(backend, graph);
    if (obs.dispatch++ == 0) provider("dispatch", (const void *)next);
    const auto dev = ggml_backend_get_device(backend);
    const bool cpu = dev && ggml_backend_dev_type(dev) == GGML_BACKEND_DEVICE_TYPE_CPU;
    if (!cpu || obs.in_cpu_dispatch) ++obs.bad_backend;
    obs.in_cpu_dispatch = cpu;
    const auto status = next(backend, graph);
    obs.in_cpu_dispatch = false;
    if (status != GGML_STATUS_SUCCESS) ++obs.bad_backend;
    return status;
}
static bool observe(ggml_tensor *t, bool ask, void*) {
    if(t->op != GGML_OP_MUL_MAT) return false;
    if(!obs.decoding) { ++other_mm; return true; }
    if(ask) {
        if(obs.asked || obs.returned) ++obs.bad;
        obs.asked=t;
        ++obs.asks;
        return true;
    }
    const auto bt = t->buffer ? ggml_backend_buffer_get_type(t->buffer) : nullptr;
    const auto dev = bt ? ggml_backend_buft_get_device(bt) : nullptr;
    if(dev && ggml_backend_dev_type(dev)==GGML_BACKEND_DEVICE_TYPE_CPU) ++obs.buf_cpu;
    else ++obs.buf_other;
    if(obs.asked==t && obs.returned && !obs.in_cpu_dispatch) ++obs.matches;
    else ++obs.bad;
    obs.asked=nullptr;
    obs.returned=false;
    return true;
}
static void close_probe() {
    obs.decoding=false;
    if (obs.asked || obs.returned || obs.in_cpu_dispatch) ++obs.bad;
    printf("EXEC %d %d %d %d %d %d %d %d %d\n", obs.pass, obs.asks, obs.kernels,
           obs.matches, obs.bad, obs.dispatch, obs.bad_backend, obs.buf_cpu, obs.buf_other);
    cpu_mm += obs.matches;
    other_mm += obs.bad + obs.bad_backend;
}
"""


def instrument(driver):
    guard.require("ggml_compute_forward_mul_mat" not in driver, "already instrumented")
    start = "static bool observe(ggml_tensor *t, bool ask, void*)"
    end = "int main(int argc,char **argv)"
    run = "        if(llama_decode(ctx,batch))return 7;"
    for token in (start, end, run):
        guard.require(driver.count(token) == 1, "fixture driver shape")
    before, body = driver.split(start)
    original, after = body.split(end)
    guard.require("ggml_backend_buft_get_device" in original, "original observer")
    return (before + HOOK + end + after).replace(
        run,
        "        obs={}; obs.decoding=true; obs.pass=pass;\n" + run + "\n        close_probe();",
    )


def evidence(log, libs):
    providers, counters = [], []
    for line in log.splitlines():
        if line.startswith("PROVIDER "):
            _, role, name = line.split(maxsplit=2)
            providers.append((role, Path(name).resolve()))
        elif line.startswith("EXEC "):
            counters.append(tuple(map(int, line.split()[1:])))
    expected = [
        ("dispatch", (libs / "libggml-base.so.0").resolve()),
        ("kernel", (libs / "libggml-cpu.so.0").resolve()),
    ]
    guard.require(providers == expected * 2, "kernel/dispatch provider")
    guard.require(len(counters) == 2, "missing decode context")
    rows = []
    for ix, row in enumerate(counters):
        p, asks, kernels, matches, bad, dispatch, wrong_backend, buf_cpu, buf_other = row
        guard.require(
            p == ix
            and asks == kernels == matches > 0
            and dispatch >= asks
            and bad == wrong_backend == 0
            and min(buf_cpu, buf_other) >= 0
            and buf_cpu + buf_other == asks,
            "kernel, scheduler or output callback mismatch",
        )
        rows.append(
            dict(
                prompt=p,
                asks=asks,
                cpu_kernel_returns=kernels,
                callback_matches=matches,
                cpu_graph_dispatches=dispatch,
                output_buffer_cpu=buf_cpu,
                output_buffer_other=buf_other,
            )
        )
    guard.require(sum(row["asks"] for row in rows) == 16, "R1 callback count")
    return rows


def extend_mapping_check(original, out, r, r1, libs):
    arms = iter(("stock", "OFF", "ON"))
    prior = (r1 / "stock/logits.f32").read_bytes()

    def check(log, size, lazy):
        name = next(arms)
        result = original(log, size, lazy)
        guard.require(lazy == (name == "ON"), "arm order")
        guard.require((out / name / "logits.f32").read_bytes() == prior, "R1 64-logit reference")
        r["arms"][name]["execution_by_prompt"] = evidence(log, libs)
        return result

    return check


def execute(a, out, r, r1):
    stock, overlay = a.stock_build_root.resolve(), a.overlay_root.resolve()
    source = guard.UPSTREAM / "tiny_fixture.py"
    guards = {
        "resident_runner_sha256": (HERE / "runner.py", GUARD_SHA),
        "protocol_sha256": (HERE / "attribution-protocol.md", PROTOCOL_SHA),
        "upstream_fixture_sha256": (source, guard.TINY_SHA),
        "build_receipt_sha256": (overlay / "receipt.json", guard.BUILD_SHA),
        "r1_receipt_sha256": (r1 / "receipt.json", R1_RECEIPT),
        "r1_logits_sha256": (r1 / "stock/logits.f32", R1_LOGITS),
        "r1_stdout_sha256": (r1 / "stock/stdout", R1_STDOUT),
    }
    r.update(
        commit=guard.git("rev-parse", "HEAD"),
        tree=guard.git("rev-parse", "HEAD^{tree}"),
        clean=not guard.git("status", "--porcelain=v1", "--untracked-files=normal"),
        program_sha256=guard.sha(Path(__file__)),
        resident_protocol_sha256=guard.sha(HERE / "protocol.md"),
        upstream_protocol_sha256=guard.sha(guard.UPSTREAM / "protocol.md"),
    )
    guard.require(r["clean"], "dirty measurement checkout")
    for name, (file, expected) in guards.items():
        r[name] = guard.sha(file)
        guard.require(r[name] == expected, "pinned input " + name)
    cg = guard.actual_scope(a.scope_unit)
    before = r["initial"] = guard.snapshot(cg)
    guard.validate(before)
    hard = resource.getrlimit(resource.RLIMIT_AS)[1]
    guard.require(hard == resource.RLIM_INFINITY or hard >= guard.ADDRESS, "inherited address cap")
    guard.save(out / "admission.json", r)
    try:
        spec = importlib.util.spec_from_file_location("pinned_tiny_attribution", source)
        tiny = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tiny)
        tiny.bounded = guard.child_limits
        tiny.DRIVER = instrument(tiny.DRIVER)
        tiny.mapped = extend_mapping_check(tiny.mapped, out, r, r1, stock / "build/bin")
        r["stock_pin"] = tiny.PIN
        status = tiny.check_run(stock, overlay, out, r)
        guard.require(
            status == guard.SUCCESS
            and r["gguf_sha256"] == guard.GGUF_SHA
            and set(r["arms"]) == {"stock", "OFF", "ON", "invalid"},
            "upstream fixture",
        )
        invalid = (out / "invalid/stdout").read_text().splitlines()
        guard.require(
            not any(line.startswith(("EXEC ", "PROVIDER ")) for line in invalid),
            "unexpected decode under invalid setting",
        )
    finally:
        guard.require(guard.actual_scope(a.scope_unit) == cg, "changed scope")
        after = r["final"] = guard.snapshot(cg)
        events = before["memory.events"]
        r["memory_events_delta"] = {k: after["memory.events"][k] - v for k, v in events.items()}
        guard.validate(after)
        guard.require(
            after["cgroup_inode"] == before["cgroup_inode"]
            and after["memory.peak"] >= before["memory.peak"]
            and all(v >= 0 for v in r["memory_events_delta"].values()),
            "scope changed or reset",
        )
    return status


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--r1-root", type=Path, required=True)
    a, rest = parser.parse_known_args()
    sys.argv[1:] = rest
    guard.execute = functools.partial(execute, r1=a.r1_root.resolve())
    return guard.main()


if __name__ == "__main__":
    raise SystemExit(main())
