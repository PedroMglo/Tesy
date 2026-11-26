"""Requalify the historical C281 session using the same driver authority as the admitted C270."""

import argparse
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SESSION = HERE.parent
Q = SESSION.parent
PROFILE = Q / "nvme_r0_gate/qualified_profile"
sys.path.insert(0, str(SESSION))

import contract  # noqa: E402
import session  # noqa: E402

# Import the same runtime authority as the current numeric gate.
sys.path.insert(0, str(PROFILE))
from authority import Authority  # noqa: E402
from run_bounded import sha256  # noqa: E402

PHYSICAL = Q / "nvme_r0_gate/driver_pair/server_startup/physical-protocol.md"
PROTOCOL_SHA = "7869c172633ed9811027c276ba0cfd8fbeb30943a59d3181d164156b8ca06cc4"
PREVIOUS_CUDA = "/usr/lib64/libcuda.so.620.70.06"
NATIVE_KEYS = {"LD_LIBRARY_PATH", "LD_DEBUG", "LD_DEBUG_OUTPUT"}
check, load, save = contract.check, contract.load, session.save


def projection(frozen):
    alias = "libcuda.so.1"
    return frozen | {"dso": frozen["dso"] | {alias: frozen["dso"][alias] | {"path": PREVIOUS_CUDA}}}


def monitor_argv(cmd, monitor_dir, native):
    check(
        set(native) == NATIVE_KEYS and native["LD_DEBUG"] == "libs", "native environment contract"
    )
    separator = cmd.index("--")
    server = cmd.index("--", separator + 1)
    check(
        cmd[separator + 1 : separator + 4]
        == [sys.executable, "-B", str(contract.REPO / "tools/run_bounded.py")],
        "monitor program changed",
    )
    check(
        cmd[server - 2 : server] == ["--env", "TESY_CPU_WAVE_SKIP_PARKED=1"],
        "historical child environment",
    )
    assignments = []
    for key in sorted(native):
        assignments += ["--env", key + "=" + native[key]]
    supervisor = [
        "/usr/bin/env",
        "-i",
        "PATH=/usr/bin:/bin",
        "LC_ALL=C",
        "HOME=" + str(Path.home()),
        "LD_LIBRARY_PATH=" + str(monitor_dir),
    ]
    return (
        cmd[: separator + 1] + supervisor + cmd[separator + 1 : server] + assignments + cmd[server:]
    )


def c270_evidence(a, protocol, sha, pre, smap):
    result = load(a.c270)
    qualified = a.c270.parent / "qualified-protocol.json"
    grade = a.c270.parent / "selected.json"
    check(sha == a.c270_sha256 and sha256(a.c270) == sha, "new C270 receipt identity")
    check(result["envelope"] == protocol["envelope"] == "E20_R0", "E20 C270 required")
    check(
        result["protocol_sha256"] == sha256(a.c270.parent / "protocol.json")
        and result["qualified_protocol_sha256"] == sha256(qualified),
        "C270 protocol identity",
    )
    check(
        result["selected_sha256"] == sha256(grade) and result["numerical_gate"] == load(grade),
        "numeric comparison identity",
    )
    session.check_gate(result["numerical_gate"])
    check(
        result["preflight_sha256"] == a.preflight_sha256
        and result["capture_sha256"] == pre["arms"]["C270"]["executable_sha256"],
        "C270 arm identity",
    )
    auth = result["authority"]
    native = pre["native_alias_sha256"]
    check(
        auth["status"] == "PASS_LIVE_AND_LOADER_C270"
        and auth["static_map_sha256"] == pre["static_map_sha256"]
        and auth["kernel"] == pre["kernel"]
        and auth["deployment_commit"] == pre["deployment_commit"],
        "C270 and C281 runtime identity differ",
    )
    check(
        auth["live_samples"] > 0 and type(auth["native_pid"]) is int and auth["native_pid"] > 0,
        "C270 live identity",
    )
    rows = auth["driver_providers"]
    absent = "libnvcuextend.so.620.70.06"
    check(
        set(rows) == set(native) | {absent} and not rows[absent]["initialized"],
        "C270 driver allowlist",
    )
    check(
        all(not rows[k]["requested"] or rows[k]["initialized"] for k in native)
        and all(rows[k]["initialized"] for k in ("libcuda.so.1", "libnvidia-ptxjitcompiler.so.1")),
        "C270 required providers",
    )
    q = load(qualified)
    check(
        q["preflight_sha256"] == a.preflight_sha256
        and q["static_map_sha256"] == pre["static_map_sha256"]
        and q["driver_deployment"] == auth["deployment_commit"]
        and q["kernel"] == auth["kernel"]
        and q["base_protocol_sha256"] == result["protocol_sha256"],
        "C270 qualified profile",
    )
    unit = protocol["execution_scope_unit"]
    check(unit == Path(unit).name and unit.startswith("tesy-"), "C270 unit identity")
    raw = a.c270.parent / "raw"
    mpath, lpath = raw / (unit + ".json"), raw / (unit + ".launch.json")
    check(
        sha256(mpath) == result["monitor_sha256"] and sha256(lpath) == result["launch_sha256"],
        "C270 launch/monitor identity",
    )
    prefix = Path(q["native_explicit_env"]["LD_DEBUG_OUTPUT"])
    check(
        prefix.parent.resolve(strict=True) == raw.resolve(strict=True)
        and sha256(prefix.parent / (prefix.name + "." + str(auth["native_pid"])))
        == auth["loader_sha256"],
        "C270 loader raw identity",
    )
    launch, manifest = load(lpath), load(mpath)
    check(
        launch["process_identity"]["pid"] == auth["native_pid"]
        and manifest["returncode"] == 0
        and manifest["stop_reason"] is None
        and manifest["mapped_libraries_match_ldd"],
        "C270 final monitor differs",
    )
    check(
        protocol["start_inventory"]["policy_sha256"]
        == sha256(a.c270.parent / "resource-policy.json")
        and protocol["pinned"]["server_sha256"] == pre["arms"]["C281"]["executable_sha256"],
        "C270 policy/server differs",
    )
    check(smap["arms"]["C270"]["executable_sha256"] == result["capture_sha256"], "C270 static map")
    return {
        "c270_sha256": sha,
        "c270_authority": auth["status"],
        "c270_loader_sha256": auth["loader_sha256"],
        "selected_sha256": result["selected_sha256"],
    }


class Runtime:
    def __init__(self, a, out):
        check(sha256(PHYSICAL) == PROTOCOL_SHA, "physical pre-registration")
        self.authority = Authority(contract.REPO, a.preflight_dir, a.preflight_sha256, "C281")
        self.pre = load(a.preflight_dir / "receipt.json")
        self.smap = load(a.preflight_dir / "static-map.json")
        check(
            sha256(a.preflight_dir / "receipt.json") == a.preflight_sha256
            and sha256(a.preflight_dir / "static-map.json") == self.pre["static_map_sha256"]
            and self.pre["status"] == "PASS_STATIC_C270_C281_DRIVER_SELECTION",
            "static authority",
        )
        self.prefix = out / "raw" / "loader"
        self.out = out
        self.pid = None
        self.last_seen = False
        self.seen = set()
        self.proof = dict(
            protocol_sha256=PROTOCOL_SHA,
            preflight_sha256=a.preflight_sha256,
            static_map_sha256=self.pre["static_map_sha256"],
            kernel=self.pre["kernel"],
            deployment_commit=self.pre["deployment_commit"],
        )
        self.native = self.authority.child_env(self.prefix)

    def selection(self, exe):
        arm = self.smap["arms"]["C281"]
        check(
            Path(exe).resolve(strict=True) == Path(arm["executable"])
            and sha256(exe) == arm["executable_sha256"],
            "selected C281 executable",
        )
        self.authority.recheck()
        links = {k: Path(v[1]) for k, v in arm["links"].items() if k != "ld-linux-x86-64.so.2"}
        return links, ["ld-linux-x86-64.so.2", "linux-vdso.so.1"]

    historical_projection = staticmethod(projection)

    def bind_c270(self, a, g, g_sha):
        self.proof.update(c270_evidence(a, g, g_sha, self.pre, self.smap))
        self.authority.recheck()
        self.proof["monitor"] = self.authority.monitor_proof()
        save(self.out / "qualified-start.json", self.proof)

    def monitor_command(self, cmd, out):
        check(
            out == self.out and self.native["LD_LIBRARY_PATH"] == self.authority.native_search,
            "native search differs",
        )
        return monitor_argv(cmd, self.authority.monitor_dir, self.native)

    def witness(self, pid, point, name):
        mapped = self.authority.live(pid)
        check(self.authority.initial <= mapped, "missing startup object at " + point)
        self.seen.update(mapped)
        save(
            self.out / name,
            dict(
                pid=pid,
                point=point,
                mapped_sha256={
                    Path(path).name: self.authority.files[path]["sha256"] for path in sorted(mapped)
                },
            ),
        )

    def first(self, pid):
        if self.pid is None:
            self.pid = pid
            self.authority.recheck()
            self.witness(pid, "READY_BEFORE_FIRST_POST", "first-client-map.json")
        else:
            check(pid == self.pid, "listener changed")

    def last(self, pid):
        check(self.pid == pid and not self.last_seen, "first/last PID")
        self.witness(pid, "AFTER_SECOND_ACCEPT_BEFORE_STOP", "last-client-map.json")
        self.last_seen = True

    def finish(self, identity, manifest, out, rid):
        check(self.pid == identity["pid"] and self.last_seen, "client map observations missing")
        check(
            manifest["explicit_env"] == {"TESY_CPU_WAVE_SKIP_PARKED": "1", **self.native},
            "server environment",
        )
        self.authority.recheck()
        diag = self.authority.audit(self.prefix, self.pid)
        check(
            set(diag["initialized_sha256"]) >= {Path(p).name for p in self.seen},
            "mapped ELF missing in loader journal",
        )
        check(
            manifest["process_identity"] == identity
            and manifest["relevant_environment"].get("LD_LIBRARY_PATH")
            == self.authority.native_search
            and "LD_PRELOAD" not in manifest["relevant_environment"],
            "native manifest and process",
        )
        save(out / "qualified-loader.json", diag)
        return dict(
            self.proof,
            status="PASS_LIVE_AND_LOADER_C281",
            native_pid=self.pid,
            first_client=sha256(out / "first-client-map.json"),
            last_client=sha256(out / "last-client-map.json"),
            loader_audit_sha256=sha256(out / "qualified-loader.json"),
            loader_raw_sha256=sha256(Path(str(self.prefix) + "." + str(self.pid))),
            original_monitor_sha256=sha256(out / "raw" / (rid + ".json")),
        )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "window", "placement", "c270", "preflight-dir", "new-output-dir"):
        ap.add_argument("--" + name, required=True, type=Path)
    for name in ("commit", "unit", "preflight-sha256", "c270-sha256"):
        ap.add_argument("--" + name, required=True)
    ap.add_argument("--window-sha256", required=True)
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    started = time.monotonic()
    try:
        check(
            a.repo.resolve(strict=True) == contract.REPO
            and session.git(contract.REPO, "rev-parse", "HEAD") == a.commit
            and not session.git(contract.REPO, "status", "--porcelain"),
            "measurement checkout",
        )
        check(not session.relevant_environment(os.environ), "inherited runtime override")
        check(sha256(a.window / "receipt.json") == a.window_sha256, "current C55 digest")
        runtime = Runtime(a, out)
        if a.execute:
            result = session.campaign(a, out, runtime=runtime)
        else:
            frozen = contract.sources(runtime.selection)
            check(
                contract.source_digest(projection(frozen))
                == load(SESSION / "inputs.json")["actual_inputs_sha256"],
                "historical input proof",
            )
            g, g_sha = session.validate_c270(a.c270)
            prior = c270_evidence(a, g, g_sha, runtime.pre, runtime.smap)
            _, model_id = contract.placement(a.window, a.placement)
            check(g["model_stat"] == model_id, "model/placement identity")
            result = dict(status="PREPARED_ONLY", model_launches=0, **prior)
    except Exception as exc:
        result = dict(
            status="FAIL_PRESERVED",
            failure=f"{type(exc).__name__}: {exc}",
            model_launches=len(list(out.glob("raw/*.launch.json"))),
        )
    result["envelope_s"] = time.monotonic() - started
    if result["envelope_s"] > 650:
        result.update(status="FAIL_PRESERVED", failure="650s envelope")
    save(out / "receipt.json", result)
    print(result["status"], flush=True)
    return int(result["status"] not in {"PREPARED_ONLY", "PASS_TWO_NATURAL_REQUESTS_LOCAL_HISTORY"})


if __name__ == "__main__":
    sys.exit(main())
