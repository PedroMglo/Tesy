"""Compare the corrected C281 conversation, its serial ablation and two independent controls."""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
OFF = run_path(str(HERE / "off.py"))
H = OFF["F"]["F"]
G, need, sha, save = (H[k] for k in ("G", "need", "sha", "save"))
SERIAL = "8ba42406e1ebd8e81b7cde38df0ab723b812e6e92286e9f132e1d922843c23e3"
METHOD = OFF["METHOD"]
REPORT_FIXTURE = "1625bd50519896b2c6214c5ea664571cf8fec41eaa53f46c17335ea3bc17d714"
REPORT_PROTOCOL = "93e082e65634b1178a8b9d0163028a0daca4052508ceaba9cf4e350e7005f37f"


class Runtime(H["Runtime"]):
    def __init__(self, a, root, mode):
        self.target = G["read"](a.qualified / "receipt.json", OFF["QUALIFIED"])
        self.serial = G["read"](a.off / "receipt.json", SERIAL)
        self.images = G["read"](a.client / "receipt.json", OFF["N"]["BUILD"])["images"]
        need(
            self.target["status"] == "GO_CPU_ROWS_NATURAL_CUT_ONLY"
            and self.target["model_starts"] == 3
            and self.target["arms"]["ROWS"]["parity_vs_P"]
            and not self.target["arms"]["B"]["parity_vs_P"]
            and self.serial["loader_probe_sha256"] == OFF["PROBE"]
            and self.serial["status"] == "GO_CPU_ELF_WITH_BLOCK_OFF"
            and self.serial["qualified_sha256"] == OFF["QUALIFIED"]
            and self.serial["model_starts"] == 1
            and self.serial["arm"]["image_sha256"]
            == self.target["arms"]["ROWS"]["image_sha256"]
            == self.images["CPU"]["image_sha256"],
            "numerical qualifications",
        )
        super().__init__(a, root, mode)
        self.auth.loader_cache = OFF["qualified_cache"](a.loader_probe)
        save(root / "loader-data-before.json", self.auth.loader_cache.receipt())

    def finish(self, ident, monitor, out, rid):
        proof = super().finish(ident, monitor, out, rid)
        proof["loader_data"] = self.auth.loader_cache.receipt()
        save(out / "runtime-proof.json", proof)
        save(out / "loader-data-after.json", proof["loader_data"])
        return proof

    def block_image(self):
        return self.images["CPU"]

    def block_flags(self):
        return super().block_flags() | {OFF["N"]["E"]["SWITCH"]: "1"}

    def numeric(self, path):
        if self.mode == "R":
            return super().numeric(path)
        target = {"ON": "ROWS", "OFF": "OFF", "P": "P"}[self.mode]
        if self.mode == "OFF":
            base, gate, digest = self.a.off, self.serial, SERIAL
        else:
            base, gate, digest = self.a.qualified, self.target, OFF["QUALIFIED"]
        key = target + "/natural-resource.json"
        cfg = G["read"](base / key, gate["files"][key])
        need(cfg["output_reserve"] == (3 if self.mode == "ON" else 1), "natural output reserve")
        return cfg, digest

    def bind_c270(self, _a, cfg, digest):
        expected = {
            "R": H["PK"]["REFERENCE"],
            "P": OFF["QUALIFIED"],
            "OFF": SERIAL,
            "ON": OFF["QUALIFIED"],
        }
        img = self.dso["libllama.so.0"]
        need(
            digest == expected[self.mode]
            and cfg["pinned"]["model_sha256"] == self.base["model_sha256"]
            and cfg["pinned"]["server_sha256"] == self.base["binary_sha256"]
            and cfg["pinned"]["startup_dso_sha256"][Path(img["path"]).name] == img["sha256"]
            and all(
                any(
                    Path(provider["path"]).name == name and provider["sha256"] == fingerprint
                    for provider in self.dso.values()
                )
                for name, fingerprint in cfg["pinned"]["startup_dso_sha256"].items()
            ),
            "real numeric provider",
        )
        self.recheck()

    def monitor_command(self, cmd, out):
        cmd = super().monitor_command(cmd, out)
        k = cmd.index("--")
        cmd[k:k] = ["-p", "LimitCORE=0", "-p", "CoredumpFilter=0x0"]
        return cmd


def wait_port(root, prev, digest):
    folder = root / prev
    arm = G["read"](folder / "receipt.json", digest)
    preset = G["read"](folder / "preset.json", arm["preset_sha256"])
    proof = arm["runtime_authority"]
    pid = proof["signal"]["pid"]
    need(
        arm["cleanup"] == "SERVER_EXIT_0_OWNER_STOP_UNIT_CLOSED_PORT_AVAILABLE"
        and proof["cuts"][-1]["pid"] == pid,
        "previous closed owner",
    )
    tc = H["TRANS"]
    checks = run_path(
        str(tc["INTEGRATED"] / "t1_manager_bank/policy_snapshot/natural/acquisition_port.py")
    )
    marks = dict(previous=prev, port=H["SESSION"].PORT, pid=pid)
    try:
        checks["transition"](
            H["SESSION"].idle_port,
            marks["port"],
            lambda: checks["verify_owner"](preset["run_id"], pid),
            marks,
        )
    finally:
        save(root / (prev + "-closed-endpoint.json"), marks)


def check_input(a, root, actual):
    if a.prepare_only:
        return
    prep = G["read"](a.prepared / "receipt.json", a.prepared_sha256)
    need(
        prep["status"] == "PREPARED_FOUR_ARMS"
        and prep["model_starts"] == 0
        and prep["commit"] == a.commit,
        "approved preflight",
    )
    key = a.mode + "/arm-inputs.json"
    old = G["read"](a.prepared / key, prep["raw_sha256"][key])

    def normalized(record, folder):
        env = dict(record["env"])
        need(
            env.pop("LD_DEBUG_OUTPUT") == str(folder / "raw/loader"),
            "bound loader trace destination",
        )
        return record | {"env": env}

    need(
        normalized(actual, root) == normalized(old, a.prepared / a.mode),
        "prepared argv, providers, resources or flags changed",
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in (
        "qualified",
        "off",
        "loader-probe",
        "report-fixture",
        "static",
        "capture",
        "verified",
        "physical",
        "plan",
        "client",
        "derived",
        "constructor",
        "window",
        "placement",
        "c270",
        "new-output-dir",
    ):
        p.add_argument("--" + k, type=Path, required=True)
    for k in ("commit", "window-sha256", "unit"):
        p.add_argument("--" + k, required=True)
    p.add_argument("--mode", choices=H["MODES"])
    p.add_argument("--prepare-only", action="store_true")
    p.add_argument("--prepared", type=Path)
    p.add_argument("--prepared-sha256")
    a = p.parse_args()
    os.umask(0o077)
    root = a.new_output_dir.resolve()
    root.mkdir()
    t = time.monotonic()
    r = dict(
        status="FAIL_PRESERVED",
        commit=a.commit,
        mode=a.mode,
        unit=a.unit,
        protocol_sha256=METHOD,
        long_gate_sha256=OFF["QUALIFIED"],
        serial_gate_sha256=SERIAL,
        loader_probe_sha256=OFF["PROBE"],
        report_fixture_sha256=REPORT_FIXTURE,
        report_protocol_sha256=REPORT_PROTOCOL,
        arms={},
    )
    try:
        fixture = G["read"](a.report_fixture / "receipt.json", REPORT_FIXTURE)
        need(
            fixture["status"] == "GO_REPORT_FIXTURE_ONLY"
            and fixture["protocol_sha256"] == sha(HERE / "report_protocol.md") == REPORT_PROTOCOL
            and fixture["physical_http_requests"] == 2
            and fixture["model_starts"] == 0,
            "recovered client reports",
        )
        window = G["read"](a.window / "receipt.json", a.window_sha256)
        need(
            window["status"] == "PASS_RESOURCE_WINDOW_ONLY"
            and sha(a.window / "samples.jsonl") == window["window_sha256"],
            "resource window",
        )
        need(a.prepare_only or (a.prepared and a.prepared_sha256), "four-arm preflight required")
        if a.mode:
            r.update(
                H["arm"](
                    a,
                    root,
                    a.mode,
                    runtime=Runtime,
                    method=METHOD,
                    protocol=HERE / "protocol.md",
                    input_check=lambda record: check_input(a, root, record),
                )
            )
        else:
            for i, mode in enumerate(H["MODES"]):
                if i and not a.prepare_only:
                    prev = H["MODES"][i - 1]
                    wait_port(root, prev, r["arms"][prev]["sha256"])
                args = sys.argv[1:].copy()
                args[args.index("--new-output-dir") + 1] = str(root / mode)
                args[args.index("--unit") + 1] = a.unit + "-" + mode.lower()
                remaining = 2700 - (time.monotonic() - t)
                need(remaining > 0, "family deadline")
                child = subprocess.run(
                    [sys.executable, "-IB", __file__, *args, "--mode", mode],
                    timeout=min(650, remaining),
                )
                item = H["read"](root / mode / "receipt.json")
                r["arms"][mode] = dict(
                    status=item["status"], sha256=sha(root / mode / "receipt.json")
                )
                need(child.returncode == 0, mode + ": " + item.get("error", item["status"]))
            r["status"] = "PREPARED_FOUR_ARMS" if a.prepare_only else "GO_FOUR_NATURAL_DIAGNOSTICS"
    except Exception as exc:
        r.update(status="FAIL_PRESERVED", error=f"{type(exc).__name__}: {exc}")
    r.update(
        wall_s=time.monotonic() - t,
        model_starts=len(list(root.rglob("*.launch.json"))),
        started_requests=len(list(root.rglob("T*-request.jsonl"))),
        raw_sha256={
            str(k.relative_to(root)): sha(k) for k in sorted(root.rglob("*")) if k.is_file()
        },
    )
    save(root / "receipt.json", r)
    print(r["status"], r.get("error", ""), flush=True)
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
