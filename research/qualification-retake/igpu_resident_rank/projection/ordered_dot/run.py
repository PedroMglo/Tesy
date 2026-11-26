"""Run the qualified e28 RADV executable with only its projection-module argument changed."""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
STOCK = run_path(HERE.parent / "radv/run.py")
B, BASE = STOCK["B"], STOCK["BASE"]
sha, need, save = (B[k] for k in ("sha", "need", "save"))
RHS = run_path(HERE.parents[1] / "rhs_device/compile_shader.py")
CPU_RECEIPT = "34f504b177c8878290513a8aa45d725cf54eae5915ba9f351579f503b5dd2ca7"
GOLD = "756c8384a4cda89c62040a81d3e45dd06e0707121dcbadecc73d45ecec0e1db3"
Q8 = "2a8187b4c60ab35286840ce35ba28d8671ff7a6a07149cf59abfdf4009cea6ef"


def sealed(path, expected):
    need(path.is_file() and not path.is_symlink() and sha(path) == expected, "sealed " + path.name)
    return path


def receipt(directory, digest, status):
    row = json.loads(sealed(directory / "receipt.json", digest).read_bytes())
    need(row["status"] == status, "required receipt status " + status)
    return row


def files(directory, manifest):
    for name, digest in manifest.items():
        need(Path(name).name == name, "basename")
        sealed(directory / name, digest)


def score_outputs(correct, wrong, gpu_q8, stock_q8, gold, cpu_q8):
    score = STOCK["compare"](correct, wrong, gold, gpu_q8, cpu_q8)
    # The historical decision labels its own shader. Only its measured quantities are shared.
    del score["decision"]
    score["identical_to_stock_q8_1"] = gpu_q8 == stock_q8
    need(
        score["identical_to_stock_q8_1"]
        and score["q8_scale_mismatch"] == 0
        and score["q8_codes_mismatch"] == 0,
        "RHS control requires 3312 stock bytes and 90 CPU blocks",
    )
    score["decision"] = (
        "NO_GO_BITWISE_ORDERED_PROJECTION"
        if score["unequal_rows"]
        else "GO_ORDERED_E28_PROJECTION_ONLY"
    )
    return score


def check_stock_pin(stock_checkout, ident):
    rel = Path("research/qualification-retake/igpu_resident_rank")
    dep = ident["deployment"]
    bound = dep["deployment"]
    # The upstream seal includes its own clean Git tree, so evaluate it at that tree.
    cmd = ["git", "--no-optional-locks", "-C", str(stock_checkout)]
    actual = subprocess.check_output(
        [*cmd, "rev-parse", "HEAD", "HEAD^{tree}"], text=True
    ).splitlines()
    need(
        actual == [bound["commit"], bound["tree"]]
        and not subprocess.check_output([*cmd, "status", "--porcelain"]),
        "qualified stock checkout",
    )
    for rank in (stock_checkout / rel, HERE.parents[1]):
        files(rank / "projection/radv", ident["sources"])
        files(rank / "rhs_device", dep["sources"])
        sealed(rank / "run.py", bound["runner"])
    original = run_path(stock_checkout / rel / "projection/radv/build.py")
    need(original["pin"]() == ident, "original executable and shader build inputs")


def authenticate(a):
    need(
        a.build_sha256 == "65a34219018b3e856ed18bebf9d3fe03b0ec5a8d5ed9cfd0b28bc50fc615d58e"
        and a.stock_sha256 == "b8316f5859bc4573acbdb26644a64d2e41a3f1085b35a8ef7e9680f679bf1fb8",
        "qualified stock R02 pair",
    )
    stock_build = receipt(a.build_dir, a.build_sha256, "PASS_RADV_PROJECTION_BUILD_ONLY")
    check_stock_pin(a.stock_checkout, stock_build["inputs"])
    files(a.build_dir, stock_build["files"])
    stock = receipt(a.stock_dir, a.stock_sha256, "MEASURED_RADV_E28_PROJECTION")
    need(
        stock["build_sha256"] == a.build_sha256
        and stock["cpu_sha256"] == a.cpu_sha256
        and stock["input_sha256"] == STOCK["X"]
        and stock["gold_sha256"] == GOLD
        and stock["cpu_q8_sha256"] == Q8,
        "stock arm lineage",
    )
    files(a.stock_dir, stock["files"])
    need(
        STOCK["review"]((a.stock_dir / "native.tsv").read_text()) == stock["proof"],
        "stock device proof",
    )
    need(a.cpu_sha256 == CPU_RECEIPT, "original CPU receipt identity")
    cpu = receipt(a.cpu_dir, a.cpu_sha256, "PASS_CPU0_E28_PROJECTION_REFERENCE")
    gd = a.cpu_dir / "ALIAS/projection"
    observed = cpu["arm"]["projection"]
    need(
        json.loads((gd / "gate.json").read_bytes()) == observed
        and observed["gate_sha256"] == observed["single_sha256"] == GOLD
        and observed["q8_sha256"] == Q8
        and observed["weight_sha256"] == STOCK["WEIGHT"]
        and observed["x_sha256"] == STOCK["X"],
        "original gate authority",
    )
    gold = sealed(gd / "gate-rank0.f32", GOLD).read_bytes()
    sealed(gd / "single-rank0.f32", GOLD)
    q8 = sealed(gd / "activation.q8", Q8).read_bytes()
    ar = receipt(a.arithmetic_dir, a.arithmetic_sha256, "PASS_C269_GATE_ARITHMETIC")
    need(
        ar["gate_sha256"] == GOLD
        and ar["q8_sha256"] == Q8
        and ar["f32_rows_equal"] == 2880
        and ar["q8_blocks_equal"] == 90
        and ar["activation_sha256"] == STOCK["X"]
        and ar["weights_sha256"] == STOCK["WEIGHT"],
        "independent arithmetic reference",
    )
    files(HERE.parent / "reference", ar["program_sha256"])
    sealed(a.arithmetic_dir / "gate.f32", GOLD)
    sealed(a.arithmetic_dir / "activation.q8", Q8)
    sq = (a.stock_dir / "actual.q8_1").read_bytes()
    measured = STOCK["compare"](
        (a.stock_dir / "correct.f32").read_bytes(),
        (a.stock_dir / "wrong.f32").read_bytes(),
        gold,
        sq,
        q8,
    )
    need(
        measured == stock["score"]
        and not measured["q8_codes_mismatch"]
        and not measured["q8_scale_mismatch"],
        "stock byte/score reproduction",
    )
    nb = receipt(a.ordered_dir, a.ordered_sha256, "PASS_ORDERED_SHADER_BUILD")
    module = sealed(a.ordered_dir / "gate.spv", nb["module_sha256"])
    sealed(HERE / "build.py", nb["build_source_sha256"])
    sealed(HERE / "gate.comp", nb["source_sha256"])
    inspect = run_path(HERE / "build.py")["inspect"]
    witness = inspect(module.read_bytes())
    need(
        all(nb[k] == v for k, v in witness.items()) and module.stat().st_size == nb["module_bytes"],
        "ordered SPIR-V witness",
    )
    sealed(HERE / "protocol.md", nb["protocol_sha256"])
    need(
        nb["compiler_sha256"] == RHS["COMPILER_SHA"] == sha(RHS["SHADERC"])
        and nb["module_sha256"] != stock_build["files"]["projection.spv"],
        "distinct module and authenticated shaderc",
    )
    sealed(a.reference_dir / "plan.json", STOCK["PLAN"])
    x = sealed(a.reference_dir / "attn_post_norm.bin", STOCK["X"])
    return dict(
        module=module,
        x=x,
        gold=gold,
        cpu_q8=q8,
        stock_q8=sq,
        stock=stock,
        module_sha256=nb["module_sha256"],
        stock_build=stock_build,
        ordered=nb,
    )


def command(a, x, out, module, layers, unit):
    return [
        "/usr/bin/systemd-run",
        "--user",
        "--scope",
        "--quiet",
        "--unit",
        unit,
        "-p",
        "MemoryMax=134217728",
        "-p",
        "MemoryHigh=134217728",
        "-p",
        "MemorySwapMax=0",
        "--",
        "/usr/bin/env",
        "-i",
        "PATH=/usr/bin:/bin",
        "LC_ALL=C",
        "VK_DRIVER_FILES=" + str(BASE["ICD"]),
        "VK_LAYER_PATH=" + str(layers),
        "VK_IMPLICIT_LAYER_PATH=" + str(layers),
        "VK_LOADER_LAYERS_DISABLE=~implicit~",
        "MESA_SHADER_CACHE_DISABLE=true",
        "/usr/bin/timeout",
        "-k",
        "1s",
        "9s",
        str(a.build_dir / "projection"),
        str(x),
        str(a.build_dir / "shared.spv"),
        str(a.build_dir / "subgroup.spv"),
        str(out / "actual.q8_1"),
        str(a.pack),
        str(module),
        str(out / "correct.f32"),
        str(out / "wrong.f32"),
    ]


def run(a, out):
    repo = HERE.parents[4]
    git = ["git", "--no-optional-locks", "-C", str(repo)]
    need(not subprocess.check_output([*git, "status", "--porcelain"]), "clean ordered checkout")
    head, tree = subprocess.check_output(
        [*git, "rev-parse", "HEAD", "HEAD^{tree}"], text=True
    ).splitlines()
    auth = authenticate(a)
    unit = "tesy-igpu-rank-" + out.name
    need(unit.replace("-", "").isalnum() and len(unit) < 165, "scope identity")
    layers = out / "empty-layers"
    layers.mkdir()
    args = command(a, auth["x"], out, auth["module"], layers, unit)
    save(out / "before.json", BASE["inventory"]())
    start = time.monotonic_ns()
    with (out / "native.tsv").open("xb") as stdout, (out / "native.stderr").open("xb") as stderr:
        child = subprocess.run(args, stdout=stdout, stderr=stderr, timeout=15, check=False)
    elapsed = time.monotonic_ns() - start
    save(out / "after.json", BASE["inventory"]())
    scope = subprocess.run(
        ["systemctl", "--user", "show", unit + ".scope", "-p", "ActiveState", "-p", "SubState"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    ).stdout
    need("ActiveState=inactive" in scope and "SubState=dead" in scope, "scope cleanup")
    log = (out / "native.tsv").read_text()
    if (
        child.returncode == 3
        and log.splitlines()
        and log.splitlines()[-1].startswith("NOT_ADMITTED\t")
    ):
        return dict(
            status="NOT_ADMITTED_ORDERED_PROJECTION",
            reason=log.splitlines()[-1],
            scope=scope.splitlines(),
        )
    need(child.returncode == 0, f"native exit {child.returncode}, see native.tsv/stderr")
    physical = STOCK["review"](log)
    del physical["variant"]
    physical.update(projection="tesy-ordered-dot", module_sha256=auth["module_sha256"])
    # Re-authenticate executable, modules, stock, references and activation after dispatch.
    authenticate(a)
    score = score_outputs(
        (out / "correct.f32").read_bytes(),
        (out / "wrong.f32").read_bytes(),
        (out / "actual.q8_1").read_bytes(),
        auth["stock_q8"],
        auth["gold"],
        auth["cpu_q8"],
    )
    return dict(
        status="MEASURED_ORDERED_E28_PROJECTION",
        commit=head,
        tree=tree,
        proof=physical,
        score=score,
        stock_build_sha256=a.build_sha256,
        stock_arm_sha256=a.stock_sha256,
        stock_module_sha256=auth["stock_build"]["files"]["projection.spv"],
        ordered_build_sha256=a.ordered_sha256,
        module_sha256=auth["module_sha256"],
        cpu_sha256=a.cpu_sha256,
        arithmetic_sha256=a.arithmetic_sha256,
        gold_sha256=GOLD,
        cpu_q8_sha256=Q8,
        scope_after=scope.splitlines(),
        wall_ns=elapsed,
        input_sha256=STOCK["X"],
        gpu_model_forwards=0,
        files={p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()},
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--preflight-only", action="store_true")
    for key in (
        "stock-checkout",
        "build-dir",
        "stock-dir",
        "ordered-dir",
        "cpu-dir",
        "arithmetic-dir",
        "reference-dir",
        "pack",
        "new-output-dir",
    ):
        ap.add_argument("--" + key, type=lambda p: Path(p).resolve(), required=True)
    for key in (
        "build-sha256",
        "stock-sha256",
        "ordered-sha256",
        "cpu-sha256",
        "arithmetic-sha256",
    ):
        ap.add_argument("--" + key, required=True)
    a = ap.parse_args()
    os.umask(0o077)
    if a.preflight_only:
        proof = authenticate(a)
        print("PASS_ORDERED_READ_ONLY_PREFLIGHT", proof["module_sha256"])
        raise SystemExit(0)
    a.new_output_dir.mkdir()
    try:
        row = run(a, a.new_output_dir)
    except Exception as e:
        row = dict(status="FAIL_PRESERVED", reason=f"{type(e).__name__}: {e}")
    save(a.new_output_dir / "receipt.json", row)
    print(row["status"], row.get("score", {}), row.get("reason", ""))
    raise SystemExit(int(row["status"] == "FAIL_PRESERVED"))
