"""Qualify a pinned full-prefix C291 image on the two independent C292 arms."""

import argparse
import os
import signal
import stat
import sys
import time
from pathlib import Path
from runpy import run_path
from types import FunctionType

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from bridge import MODES, checked, previous  # noqa: E402

P = previous()
live, base, grade, need, sha, save = (
    P[k] for k in ("live", "base", "grade", "need", "sha", "save")
)
METHOD = "4102e252fce3839adb97d845dcd1a857101c2881fc1c46785f8098ed9e016511"
PARENT_BUILD = P["BUILD"]


def bound(func, **dependencies):
    """Use the previous arm, preserving its guards, with explicit changed dependencies."""
    return FunctionType(
        func.__code__,
        func.__globals__ | dependencies,
        func.__name__,
        func.__defaults__,
        func.__closure__,
    )


class LiveOutput:
    """Bound ordinary capture files while the journal has its fixed provisional extent."""

    def __getattr__(self, name):
        return getattr(base.measure, name)

    @staticmethod
    def file_bytes(root):
        total = 0
        for directory, _, names in os.walk(root):
            for name in names:
                path = Path(directory, name)
                try:
                    info = path.lstat()
                except FileNotFoundError:
                    continue
                if path == root / "phase.pfj1":
                    need(
                        stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600,
                        "foreign journal type/mode",
                    )
                    need(info.st_size <= 134217664, "journal exceeded allocation")
                    if info.st_size == 134217664:
                        continue
                total += info.st_size
        return total


class Scope:
    """The new diagnostic mapping requires a larger per-file limit for journal creation."""

    measure = LiveOutput()

    def __getattr__(self, name):
        return getattr(base, name)

    @staticmethod
    def replace_once(command, old, new):
        need((old, new) == ("LimitFSIZE=8388608", "LimitFSIZE=33554432"), "foreign scope change")
        base.replace_once(command, old, "LimitFSIZE=134217728")


class Authority(P["NumericalAuthority"]):
    def __init__(self, args, mode, journal):
        live.CaptureAuthority.__init__(self, args, "ON")
        b = checked(args.build_dir / "receipt.json", args.build_sha256)
        need(
            b["status"] == "PASS_C291_FULL_PREFIX_DSO_STATIC_C281"
            and b["parent_build_sha256"] == PARENT_BUILD
            and b["static_preflight_sha256"] == live.static.PREFLIGHT
            and b["c292_closure_sha256"] == live.CLOSURE
            and b["original_sha256"] == P["LIBS"]["original"]
            and b["control_sha256"] == P["LIBS"]["control"]
            and b["capacity"] == 1398100
            and b["cut_call"] == 86
            and b["candidate_sha256"] not in set(P["LIBS"].values()),
            "new qualified DSO",
        )
        self.image = (args.build_dir / b["candidate_file"]).resolve(strict=True)
        self.digest = sha(self.image)
        need(self.digest == b["candidate_sha256"], "actual ELF")
        self.journal = journal if mode == "overlay_on" else None
        name = live.static.SONAME
        before = checked(args.closure_dir / "receipt.json", live.CLOSURE)["startup"]
        resolved = b["capture_startup"]
        P["validate_maps"](before, resolved, self.image, self.digest)
        alias = (args.build_dir / "libs").resolve(strict=True)
        self.new_alias, self.new_bindings = alias, {name: str(self.image)}
        live.aliases(alias, self.new_bindings)
        search = [str(alias), *self.arm["native_search"][1:]]
        listed = self.static.interpret(
            self.static.command(
                [self.static.LOADER, "--list", self.exe], self.static.environment(search)
            )
        )
        links = {k: [str(v), str(v.resolve(strict=True))] for k, v in listed.items()}
        need(
            links.keys() == resolved.keys()
            and all(links[k] == v for k, v in self.links.items() if k != name)
            and links[name] == [str(alias / name), str(self.image)]
            and all(v[1] == resolved[k]["file"] for k, v in links.items()),
            "loader selection",
        )
        self.files[str(self.image)] = live.identity(self.image) | {"sha256": self.digest}
        self.links = links
        self.arm = self.arm | {"native_search": search}
        self.native_search = ":".join(search)
        self.initial = {r[1] for r in links.values()}
        self.allowed = self.initial | set(map(str, self.drivers.values()))
        self.vma_keys = {p: live.reference_key(p, self.files[p]) for p in self.allowed}
        self.recheck()


def inspect_journal(path, enabled, pack, model):
    if not enabled:
        return P["inspect_journal"](path, False, pack, model)
    need(
        path.is_file() and not path.is_symlink() and path.stat().st_mode & 0o777 == 0o600,
        "private filtered journal",
    )
    return run_path(str(HERE.parent / "audit.py"))["audit_numeric"](path, pack, model)


def campaign(a, out, r):
    need(sha(HERE / "protocol.md") == METHOD, "protocol")
    b = checked(a.build_dir / "receipt.json", a.build_sha256)
    a.checkout, a.preflight_sha256 = live.REPO, live.static.PREFLIGHT
    need(
        base.prepare.git(live.REPO, "rev-parse", "HEAD") == a.measurement_commit
        and not base.prepare.git(live.REPO, "status", "--porcelain"),
        "clean tree",
    )
    gold = grade.reference(a.r0_dir)
    tree = P["original"](a.original_family, gold)
    bindings = P["LIBS"] | {"overlay": b["candidate_sha256"]}
    postflight = bound(P["postflight"], inspect_journal=inspect_journal)
    arm = bound(
        P["arm"],
        NumericalAuthority=Authority,
        base=Scope(),
        postflight=postflight,
        LIBS=bindings,
        BUILD=a.build_sha256,
        METHOD=METHOD,
    )
    r.update(
        independent_reference={
            "c270_receipt_sha256": grade.R0,
            "c291_family_sha256": P["FAMILY"],
            "capture_tree": tree,
        },
        build_receipt_sha256=a.build_sha256,
        candidate_sha256=b["candidate_sha256"],
        measurement_commit=a.measurement_commit,
        c55_sha256=a.window_sha256,
        protocol_sha256=METHOD,
    )
    for mode in MODES:
        folder = out / mode
        folder.mkdir()
        row = {"status": "FAIL_PRESERVED", "mode": mode}
        try:
            arm(a, folder, mode, gold, tree, row)
        except Exception as exc:
            row["reason"] = f"{type(exc).__name__}: {exc}"
            row["status"] = "FAIL_PRESERVED"
            raise
        finally:
            row["model_launch_receipts"] = len(list((folder / "raw").glob("*.launch.json")))
            save(folder / "receipt.json", row)
            r["arms"][mode] = {
                k: row[k]
                for k in ("status", "image_sha256", "journal_enabled", "capture_tree")
                if k in row
            }
            r["arms"][mode]["receipt_sha256"] = sha(folder / "receipt.json")
            r["model_launch_receipts"] += row["model_launch_receipts"]
    if a.execute:
        need(
            r["model_launch_receipts"] == 2
            and all(x["capture_tree"] == tree for x in r["arms"].values()),
            "independent arms",
        )
    r["status"] = "PASS_C292_FULL_PREFIX_NUMERIC" if a.execute else "PREPARED_ONLY"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in (
        "build-dir",
        "original-family",
        "closure-dir",
        "preflight-dir",
        "r0-dir",
        "derived-dir",
        "constructor-receipt",
        "window",
        "placement",
        "new-output-dir",
    ):
        p.add_argument("--" + k, type=Path, required=True)
    for k in ("build-sha256", "window-sha256", "measurement-commit", "unit"):
        p.add_argument("--" + k, required=True)
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)
    r = {"status": "FAIL_PRESERVED", "model_launch_receipts": 0, "arms": {}}

    def expired(*_):
        raise TimeoutError("full-prefix C292 family")

    signal.signal(signal.SIGALRM, expired)
    signal.alarm(720)
    start = time.monotonic()
    try:
        campaign(a, a.new_output_dir, r)
    except Exception as exc:
        r["reason"] = f"{type(exc).__name__}: {exc}"
    finally:
        signal.alarm(0)
        r.update(
            elapsed_s=time.monotonic() - start,
            unexecuted_arms=[m for m in MODES if m not in r["arms"]],
        )
        save(a.new_output_dir / "receipt.json", r)
    print(r["status"], r.get("reason", ""))
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
