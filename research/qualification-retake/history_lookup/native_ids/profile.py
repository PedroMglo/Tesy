"""Run the C281 reference under its original supervisor with native sample logging."""

import argparse
import hashlib
import importlib.util
import os
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUALIFICATION = HERE.parents[1]
POST_PATH = QUALIFICATION / "nvme_conversation/postupdate/profile.py"
spec = importlib.util.spec_from_file_location("c281_postupdate", POST_PATH)
post = importlib.util.module_from_spec(spec)
spec.loader.exec_module(post)
check, load, save, sha = post.check, post.load, post.save, post.sha256
HISTORY = "cb191e31c2e3ee547a01228065a3c4253bdb312dd1e561d361f75365f065356a"
C270 = "1f332ad437d90c24adf3b88b87ddf0dac8e13b7e87e818d93461ffd281c801b6"
SERVER = "054e983528d35731e2dc6222f1418f2f08120ef83e0c5f2a8db11805dd38effa"
IMPL = "6e4786b127d8a0f2addd657b9842dade1c3f2b9262d088b84fb526ca04ed9206"
PROTOCOL = "cfc1a043bb412293db4f646e6cddf1f3923e72ea12f2ae634dd56a07e3eae537"
SOURCES = {
    "common/arg.cpp": "4a964a7ca2dda07a8b3010c865363060ba43ec49b1e7322fde60d0e08d872730",
    "common/log.h": "cd065a0799ffc9a8adcb96f5188f77aec139e2520cb76316bf091ca289bb5bcb",
    "common/log.cpp": "be54107a3334c3e74439b4a3a694822e61cf918725fa401d9921a53e27d9a7fb",
    "tools/server/server-common.h": (
        "23cf04f5394609124e1b1acb872f8934e1bfa9335cc578722ab538b057e67b9e"
    ),
    "tools/server/server-context.cpp": (
        "657c331a707f0faf74615d19387088070c3dbd7559328619c9ef606a4ec8cc55"
    ),
}
FLAGS = ("-lv", "--verbosity", "--log-verbosity")


def diagnostic_args(original):
    check(
        [i for i in original if i in FLAGS] == ["-lv"]
        and original[original.index("-lv") + 1] == "3",
        "original verbosity contract",
    )
    check(
        original.count("--port") == 1 and original[original.index("--port") + 1] == "18442",
        "original port contract",
    )
    # common_params_parse_ex consumes CLI options in order. Preserve the complete original
    # invocation (including its -lv 3), then override that field alone with the debug threshold.
    return [*original, "--log-verbosity", "5"]


def argv_image(argv):
    check(all(isinstance(item, str) and item and "\0" not in item for item in argv), "invalid argv")
    return b"\0".join(os.fsencode(item) for item in argv) + b"\0"


def final_raw_bytes(directory, limit=64 * 2**20):
    total = 0
    for path in directory.iterdir():
        check(path.is_file() and not path.is_symlink(), "unexpected private raw entry")
        total += path.stat().st_size
    check(0 < total <= limit, "final combined raw budget")
    return total


def attest_history(path):
    receipt = path / "receipt.json"
    check(sha(receipt) == HISTORY, "historical C281 reference")
    r = load(receipt)
    preset = path / "preset.json"
    check(
        sha(preset) == r["preset_sha256"]
        and r["status"] == "PASS_TWO_NATURAL_REQUESTS_LOCAL_HISTORY",
        "historical preset",
    )
    p = load(preset)
    check(
        p["binary_sha256"] == SERVER
        and p["dso"]["libllama-server-impl.so"]["sha256"] == IMPL
        and p["c270_receipt_sha256"] == C270,
        "reference binaries",
    )
    for i, digest in enumerate(p["historical_inputs"], 1):
        check(sha(path / "raw" / f"T{i}-input.json") == digest, "reference input")
    for name, digest in SOURCES.items():
        check(sha(Path(p["backend"]) / name) == digest, "server source " + name)
    impl = Path(p["dso"]["libllama-server-impl.so"]["path"])
    check(
        sha(impl) == IMPL
        and impl.read_bytes().count(b"n_decoded = %d, n_remaining = %d, next token: %5d '%s'") == 1,
        "compiled sampling observation",
    )
    return p


class Runtime(post.Runtime):
    def __init__(self, a, out, reference):
        super().__init__(a, out)
        self.reference = reference
        self.command = diagnostic_args(reference["server_command"])
        self.first_cmd = None
        self.last_cmd = None

    def monitor_command(self, cmd, out):
        cmd = super().monitor_command(cmd, out)
        start = len(cmd) - len(self.reference["server_command"])
        check(
            start > 0
            and cmd[start - 1] == "--"
            and cmd[start:] == self.reference["server_command"],
            "native command before diagnostic",
        )
        return cmd[:start] + self.command

    def check_live_command(self, pid):
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        check(raw == argv_image(self.command), "live native argv")
        check(
            Path(f"/proc/{pid}/exe").resolve(strict=True)
            == Path(self.command[0]).resolve(strict=True),
            "live native executable",
        )
        return hashlib.sha256(raw).hexdigest()

    def first(self, pid):
        super().first(pid)
        digest = self.check_live_command(pid)
        if self.first_cmd is None:
            self.first_cmd = digest
        check(self.first_cmd == digest, "first client argv changed")

    def last(self, pid):
        super().last(pid)
        self.last_cmd = self.check_live_command(pid)
        check(self.first_cmd == self.last_cmd, "last client argv changed")

    def finish(self, identity, manifest, out, rid):
        result = super().finish(identity, manifest, out, rid)
        path = out / "raw" / (rid + ".stderr")
        check(
            manifest["command"] == self.command
            and self.last_cmd
            == self.first_cmd
            == hashlib.sha256(argv_image(self.command)).hexdigest(),
            "postflight command",
        )
        check(
            manifest["binary_sha256"] == SERVER
            and path == Path(manifest["stderr_path"])
            and not path.is_symlink()
            and sha(path) == manifest["output_sha256"][".stderr"]
            and 0 < path.stat().st_size <= 64 * 2**20,
            "sample log identity",
        )
        for name in ("first-client-map.json", "last-client-map.json"):
            row = load(out / name)
            check(
                row["pid"] == identity["pid"]
                and row["mapped_sha256"]["libllama-server-impl.so"] == IMPL,
                "observed server implementation",
            )
        raw_bytes = final_raw_bytes(out / "raw")
        self.observation = dict(
            combined_raw_bytes=raw_bytes,
            combined_raw_cap_bytes=64 * 2**20,
            verbosity=5,
            pid=identity["pid"],
            port=post.contract.PORT,
            native_task_source_sha256=SOURCES["tools/server/server-context.cpp"],
            argv_sha256=self.last_cmd,
            first_argv_sha256=self.first_cmd,
            last_argv_sha256=self.last_cmd,
            server_sha256=SERVER,
            server_impl_sha256=IMPL,
            stderr_sha256=sha(path),
            stderr_bytes=path.stat().st_size,
            raw_stderr_file=path.name,
        )
        return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in (
        "repo",
        "window",
        "placement",
        "c270",
        "preflight-dir",
        "historical",
        "new-output-dir",
    ):
        ap.add_argument("--" + name, type=Path, required=True)
    for name in ("commit", "unit", "preflight-sha256", "c270-sha256", "window-sha256"):
        ap.add_argument("--" + name, required=True)
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    started = time.monotonic()
    try:
        check(
            a.repo.resolve(strict=True) == post.contract.REPO
            and post.session.git(post.contract.REPO, "rev-parse", "HEAD") == a.commit
            and not post.session.git(post.contract.REPO, "status", "--porcelain"),
            "measurement checkout",
        )
        check(
            sha(HERE / "protocol.md") == PROTOCOL and a.c270_sha256 == C270,
            "protocol/C270 identity",
        )
        check(not post.session.relevant_environment(os.environ), "unexpected runtime overrides")
        check(sha(a.window / "receipt.json") == a.window_sha256, "C55 identity")
        reference = attest_history(a.historical)
        rt = Runtime(a, out, reference)
        if a.execute:
            r = post.session.campaign(a, out, runtime=rt)
            r["native_ids"] = rt.observation
            # Client latencies in the private row are diagnostic; remove M4 classifications.
            del r["nominal_first_final_le_10s"], r["nominal_decode_ge_6"]
        else:
            frozen = post.contract.sources(rt.selection)
            check(
                post.contract.source_digest(post.projection(frozen))
                == load(post.SESSION / "inputs.json")["actual_inputs_sha256"]
                and frozen["server_command"] == reference["server_command"],
                "historical C281 sources",
            )
            gate, digest = post.session.validate_c270(a.c270)
            prior = post.c270_evidence(a, gate, digest, rt.pre, rt.smap)
            _, model_id = post.contract.placement(a.window, a.placement)
            check(gate["model_stat"] == model_id, "current placement")
            r = dict(status="PREPARED_ONLY", model_launches=0, **prior)
    except Exception as exc:
        r = dict(
            status="FAIL_PRESERVED",
            failure=f"{type(exc).__name__}: {exc}",
            model_launches=len(list(out.glob("raw/*.launch.json"))),
        )
    r.update(
        envelope_s=time.monotonic() - started,
        historical_sha256=HISTORY,
        native_protocol_sha256=PROTOCOL,
        diagnostic_only=True,
        profile_sha256=sha(Path(__file__)),
    )
    if r["envelope_s"] > 650:
        r.update(status="FAIL_PRESERVED", failure="650s envelope")
    save(out / "receipt.json", r)
    print(r["status"], flush=True)
    return int(r["status"] not in {"PREPARED_ONLY", "PASS_TWO_NATURAL_REQUESTS_LOCAL_HISTORY"})


if __name__ == "__main__":
    raise SystemExit(main())
