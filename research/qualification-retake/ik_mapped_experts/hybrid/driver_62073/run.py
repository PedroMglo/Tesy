"""Run the existing 32+1 GPU bank fixture with the qualified system ELF closure."""

import argparse
import os
import subprocess
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
D = run_path(str(HERE.parent / "device/run.py"))
G = run_path(str(HERE.parent / "client/grade.py"))
SYS = run_path(str(HERE / "system.py"))
IO, need, sha, load, save = (D[k] for k in ("IO", "need", "sha", "load", "save"))
CLIENT = "5761ef3190ac8d46e26861292c5c2c1a8fb597cfbaaa5ca54849a608ee27e728"
LIBS = "5c648c09e18d29bc47d57af018053f5251f67f85bdd56cfe8f1b954c95470753"
CPU = "fe31c39297337fd024f0755eb64c1dcda5ab988a50ca563fa01d4474aa565346"
HIST = "2d165f3e9c8f8108a04e758a5496e610cdbe0051afaee1fe1da35123b8373bfd"


def arm_grade(mode, p):
    return G["check_arm"](
        mode, (p / "stdout").read_text(), (p / "stderr").read_text(), p / "native"
    )


def placement(path):
    destinations = {}
    for line in path.read_text().splitlines():
        if line.startswith("NODE "):
            _, phase, _, op, name, _, _, _, _, src, out, _ = line.split()
            k = (phase, op, name)
            need(k not in destinations, "duplicate node")
            destinations[k] = (src, out)
    need(len(destinations) == 24, "missing routed consumer")
    return destinations


def prepare(a):
    head, tree = subprocess.check_output(
        ["git", "-C", HERE, "rev-parse", "HEAD", "HEAD^{tree}"], text=True
    ).splitlines()
    need(
        head == a.commit
        and not subprocess.check_output(["git", "-C", HERE, "status", "--porcelain"]),
        "dirty or changed freeze",
    )
    need(bool(a.execute) == bool(a.prepared and a.prepared_sha256), "prepared pair required")
    old = load(a.client / "receipt.json", CLIENT)
    ds = load(a.dso / "receipt.json", LIBS)
    cpu = load(a.cpu / "receipt.json", CPU)
    hist = load(a.historical / "receipt.json", HIST)
    exe = a.client.resolve() / "hybrid-client"
    need(
        (old["status"], ds["status"], cpu["status"], hist["status"])
        == (
            "PASS_TINY_HYBRID_CLIENT_BUILD",
            "PASS_IK_SM89_LINK_ONLY",
            "PASS_TINY_HYBRID_CPU_REFERENCE",
            "PASS_TINY_HYBRID_GPU_FIXTURE",
        )
        and old["dso_build_sha256"] == LIBS
        and sha(exe) == old["binary_sha256"]
        and a.tiny.stat().st_size == 3390592
        and sha(a.tiny) == D["TINY"],
        "client, DSOs or fixture",
    )
    cpu_grade = arm_grade("CPU", a.cpu)
    need(cpu_grade == cpu["grade"], "CPU reference")
    past = {}
    for m in D["MODES"]:
        p = a.historical / m
        need(
            all(
                sha(p / file) == hist["raw_sha256"][m + "/" + file]
                for file in ("stdout", "stderr", "native/prefill.f32", "native/teacher.f32")
            ),
            "historical raw",
        )
        past[m] = arm_grade(m, p)
        need(past[m] == hist["arms"][m]["grade"], "historical GPU grade")
    env, paths, driver = SYS["system_loader"](exe, old, a.dso.resolve() / "objects")
    libs = {**paths, **driver, str(exe): old["binary_sha256"], str(a.tiny.resolve()): D["TINY"]}
    providers = {p: {"stat": IO.stat_id(Path(p)), "sha256": v} for p, v in libs.items()}
    policy, end = D["c55"](a)
    pfile = D["QUAL"] / "packed_layer_service/profile.py"
    monitor, unchanged = run_path(str(pfile))["monitor_provider"](SimpleNamespace(token=IO.stat_id))
    need(
        monitor["mode"] == "SYSTEM_NVML"
        and monitor["kernel_driver"] == SYS["VERSION"]
        and monitor["actual_nvml_sha256"]
        == driver[str(Path("/usr/lib64/libnvidia-ml.so.1").resolve())]
        and monitor["nvidia_smi_sha256"] == driver["/usr/bin/nvidia-smi"],
        "monitor identity",
    )
    state = dict(
        commit=head,
        tree=tree,
        client_sha256=CLIENT,
        dso_sha256=LIBS,
        cpu_sha256=CPU,
        history_sha256=HIST,
        tiny_sha256=D["TINY"],
        c55_sha256=a.c55_sha256,
        child_env=env,
        providers=providers,
        monitor=monitor,
        sources={
            p.name: sha(p) for p in (HERE / "protocol.md", HERE / "system.py", HERE / "run.py")
        },
        old_supervisor_sha256=sha(HERE.parent / "device/run.py"),
    )
    if a.execute:
        prior = load(a.prepared / "receipt.json", a.prepared_sha256)
        need(
            prior["status"] == "PREPARED_ONLY" and prior["authority"] == state,
            "preparation changed",
        )
    allowed = {
        p
        for p in driver
        if Path(p).name.startswith(("libcuda.", "libnvidia-")) and "nvidia-ml" not in p
    }
    return (
        state,
        (policy, end, exe, a.tiny.resolve(), env, set(paths), allowed),
        cpu_grade,
        past,
        unchanged,
    )


def run(a, out, r):
    authority, params, cpu, past, unchanged = prepare(a)
    r["authority"] = authority
    if not a.execute:
        r["status"] = "PREPARED_ONLY"
        return
    r["prepared_sha256"] = a.prepared_sha256
    IO.CAP, IO.STOPS = D["CAP"], D["STOP"]
    IO.scope()
    cg = Path("/sys/fs/cgroup") / IO.cgroup_state()["path"].lstrip("/")
    need(
        a.unit.startswith("tesy-ik-hybrid-device-")
        and cg.name == a.unit + ".scope"
        and cg.parent.name == "app.slice"
        and set((cg / "cgroup.procs").read_text().split()) == {str(os.getpid())},
        "scope",
    )
    resident = resident_grade = None
    for mode in D["MODES"]:
        unchanged()
        arm = {"starts": 0}
        r["arms"][mode] = arm
        native = D["sample_arm"](mode, out, a, *params, arm)
        grade = arm_grade(mode, native.parent)
        arm["grade"] = grade
        need(grade["host_registration_events"] == 0, "host registration")
        other = a.historical / mode
        cross = G["compare_arms"](other / "native", past[mode], native, grade)
        same_ops = placement(other / "stdout") == placement(native.parent / "stdout")
        arm["cross_driver"] = cross
        arm["same_consumer_placement"] = same_ops
        if mode == "RESIDENT":
            resident, resident_grade = native, grade
            arm["cpu"] = G["compare_arms"](a.cpu / "native", cpu, native, grade)
        else:
            local = G["compare_arms"](resident, resident_grade, native, grade)
            arm["versus_resident"] = local
            need(local["routes_equal"], "different native routes")
            if mode == "BANK9":
                need(local["bitwise"], "nine-slot parity")
            else:
                need(
                    local["rows"]["prefill.f32"]["different_first_argmax"] == 5,
                    "BANK7 counterexample",
                )
        need(cross["routes_equal"] and cross["bitwise"] and same_ops, "new driver differs")
    unchanged()
    need(
        all(IO.stat_id(Path(k)) == v["stat"] for k, v in authority["providers"].items()),
        "provider drift",
    )
    r["status"] = "PASS_SYSTEM_TINY_BANKS"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("client", "dso", "cpu", "historical", "tiny", "c55", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    for key in ("c55-sha256", "commit"):
        p.add_argument("--" + key, required=True)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--prepared", type=Path)
    p.add_argument("--prepared-sha256")
    p.add_argument("--unit", default="")
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    r = dict(status="FAIL_PRESERVED", arms={}, requests=0, energy_j=None)
    try:
        run(a, out, r)
    except Exception as exc:
        r["reason"] = f"{type(exc).__name__}: {exc}"
    finally:
        if a.execute:
            try:
                end = IO.cgroup_state()
                cg = Path("/sys/fs/cgroup") / end["path"].lstrip("/")
                r.update(
                    memory_peak_B=end["memory_peak"],
                    swap_peak_B=int((cg / "memory.swap.peak").read_text()),
                    events=end["events_local"],
                    raw_sha256={
                        str(p.relative_to(out)): sha(p) for p in out.rglob("*") if p.is_file()
                    },
                )
                need(
                    cg.name == a.unit + ".scope"
                    and not r["swap_peak_B"]
                    and not r["events"]["oom"]
                    and not r["events"]["oom_kill"]
                    and r["memory_peak_B"] < D["STOP"],
                    "end scope/resource",
                )
            except Exception as exc:
                r.update(status="FAIL_PRESERVED", final_error=str(exc))
        save(out / "receipt.json", r)
    print(r["status"], r.get("reason", ""), r.get("final_error", ""))
    return r["status"] == "FAIL_PRESERVED"


if __name__ == "__main__":
    raise SystemExit(main())
