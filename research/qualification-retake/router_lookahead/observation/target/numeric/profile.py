"""Run only the frozen C292 probe-OFF/ON pair and its independent numerical controls."""

import os
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[3]
PACK = QUAL / "igpu_resident_rank/request_budget/device/pack_native"
F = run_path(str(PACK / "full_prefix/numeric/profile.py"))
P, bound, live, base, grade, need, sha, save = (
    F[k] for k in ("P", "bound", "live", "base", "grade", "need", "sha", "save")
)
BUILD = "ac166701bf998ffdac0e4cb75a796d4208b033a573d49f16aed6329c7942978b"
IMAGE = "9b15c522ec3c407199b8438317503453cc1170594e2f5a886a2ab7822139901b"
METHOD = "c46a1bbc4ed543fe2aee5bead69dba812ac2441eb9ee370c31531e9e7722e5b1"
FLAG = "TESY_ROUTER_LOOKAHEAD"
ROUTES = "10589663e1486b87c3143cbc26ce16d9904ce289a92406169b6ee10eeb74bb3b"
DEMANDS = "b09ab591db5fc9120da676124856959cf8606a613f751ff8c27d5e57a3278894"
MODES = ("overlay_off", "overlay_on")


class Authority(P["NumericalAuthority"]):
    def __init__(self, a, mode, journal):
        live.CaptureAuthority.__init__(self, a, "ON")
        self.probe = mode == "overlay_on"
        self.journal = journal
        b = grade.read(a.build_dir / "receipt.json", BUILD)
        need(
            b["status"] == "PASS_C291_ROUTER_LOOKAHEAD_STATIC_C281"
            and b["parent_pack_build_sha256"] == P["BUILD"]
            and b["static_preflight_sha256"] == live.static.PREFLIGHT
            and b["c292_closure_sha256"] == live.CLOSURE
            and b["original_sha256"] == P["LIBS"]["original"]
            and b["control_sha256"] == P["LIBS"]["control"]
            and b["candidate_sha256"] == IMAGE
            and mode in MODES,
            "qualified router observer and mode",
        )
        self.image = (a.build_dir / b["candidate_file"]).resolve(strict=True)
        self.digest = sha(self.image)
        need(self.digest == IMAGE, "candidate ELF changed")
        name = live.static.SONAME
        before = grade.read(a.closure_dir / "receipt.json", live.CLOSURE)["startup"]
        resolved = b["capture_startup"]
        P["validate_maps"](before, resolved, self.image, self.digest)
        alias = (a.build_dir / "libs").resolve(strict=True)
        self.new_alias, self.new_bindings = alias, {name: str(self.image)}
        live.aliases(alias, self.new_bindings)
        search = [str(alias), *self.arm["native_search"][1:]]
        listing = self.static.interpret(
            self.static.command(
                [self.static.LOADER, "--list", self.exe], self.static.environment(search)
            )
        )
        links = {k: [str(v), str(v.resolve(strict=True))] for k, v in listing.items()}
        need(
            links.keys() == resolved.keys()
            and all(links[k] == v for k, v in self.links.items() if k != name)
            and links[name] == [str(alias / name), str(self.image)]
            and all(v[1] == resolved[k]["file"] for k, v in links.items()),
            "actual loader",
        )
        self.files[str(self.image)] = live.identity(self.image) | {"sha256": self.digest}
        self.links = links
        self.arm = self.arm | {"native_search": search}
        self.native_search = ":".join(search)
        self.initial = {v[1] for v in links.values()}
        self.allowed = self.initial | set(map(str, self.drivers.values()))
        self.vma_keys = {p: live.reference_key(p, self.files[p]) for p in self.allowed}
        self.recheck()

    def child_env(self, log_prefix):
        return super().child_env(log_prefix) | ({FLAG: "1"} if self.probe else {})

    def live(self, pid):
        if not self.env_checked:
            fields = (Path("/proc", str(pid), "environ")).read_bytes().split(b"\0")
            values = [x for x in fields if x.startswith((FLAG + "=").encode())]
            need(values == ([f"{FLAG}=1".encode()] if self.probe else []), "live native probe flag")
        return super().live(pid)


class Capture:
    def __getattr__(self, name):
        return getattr(base, name)

    @staticmethod
    def command(*args):
        cmd = base.command(*args)
        ctl = args[1]
        if ctl.probe:
            i = cmd.index("--", cmd.index("--env"))
            cmd[i:i] = ["--env", FLAG + "=1"]
        return cmd

    @staticmethod
    def validate_monitor(m, expected, protocol):
        need(
            m["relevant_environment"].get(FLAG) == expected.get(FLAG)
            and (FLAG not in expected or expected[FLAG] == "1"),
            "monitor probe flag",
        )
        plain = {k: v for k, v in expected.items() if k != FLAG}
        base.validate_monitor(dict(m, explicit_env=plain), plain, protocol)


def inspect_journal(path, present, pack, model):
    need(
        present and path.parent.parent.name in MODES and path.stat().st_size <= 64 + 262144 * 96,
        "journal destination/cap",
    )
    rows, header = P["pfj"].read_journal(path)
    need(all(0 < e.kind <= 36 for e in rows), "unknown PFJ event")
    legacy = [e for e in rows if e.kind <= 30]
    # All source bytes were checked by read_journal. Preserve event order for each proof.
    reader = SimpleNamespace(read_journal=lambda _: (legacy, header))
    previous = bound(P["inspect_journal"], pfj=reader)(path, True, pack, model)
    probe = path.parent.parent.name == "overlay_on"
    join = run_path(str(HERE / "join.py"))["audit"](rows, probe)
    need(join["status"] == ("PASS_LOOKAHEAD_ON" if probe else "PASS_LOOKAHEAD_OFF"), "probe join")
    need(
        join["official_ordered_sha256"] == ROUTES and join["demanded_slots_sha256"] == DEMANDS,
        "route or physical demand sequence versus independent P95",
    )
    return previous | dict(probe_enabled=probe, join=join, sha256=sha(path))


def campaign(a, out, r):
    need(a.build_sha256 == BUILD and sha(HERE / "protocol.md") == METHOD, "frozen receipts")
    need(
        not os.environ.get(FLAG)
        and not os.environ.get(P["FILE"])
        and not os.environ.get(P["TRIGGER"]),
        "inherited probe or journal",
    )
    a.checkout, a.preflight_sha256 = live.REPO, live.static.PREFLIGHT
    need(
        base.prepare.git(live.REPO, "rev-parse", "HEAD") == a.measurement_commit
        and not base.prepare.git(live.REPO, "status", "--porcelain"),
        "measurement tree",
    )
    gold = grade.reference(a.r0_dir)
    tree = P["original"](a.original_family, gold)
    ctl = Capture()
    arm = bound(
        P["arm"],
        NumericalAuthority=Authority,
        base=ctl,
        postflight=bound(P["postflight"], base=ctl, inspect_journal=inspect_journal),
        LIBS=P["LIBS"] | {"overlay": IMAGE},
        BUILD=BUILD,
        METHOD=METHOD,
    )
    r.update(
        build_receipt_sha256=BUILD,
        candidate_sha256=IMAGE,
        measurement_commit=a.measurement_commit,
        protocol_sha256=METHOD,
        c55_sha256=a.window_sha256,
        reference_tree=tree,
    )
    for mode in MODES:
        folder = out / mode
        folder.mkdir()
        row = dict(status="FAIL_PRESERVED", mode=mode)
        print(("C118/launch if admitted " if a.execute else "Preparing ") + mode, flush=True)
        try:
            arm(a, folder, mode, gold, tree, row)
        except Exception as e:
            row.update(status="FAIL_PRESERVED", reason=repr(e))
            raise
        finally:
            row["model_launch_receipts"] = len(list((folder / "raw").glob("*.launch.json")))
            save(folder / "receipt.json", row)
            r["arms"][mode] = {
                k: row[k]
                for k in ("status", "image_sha256", "capture_tree", "journal_enabled")
                if k in row
            }
            r["arms"][mode]["receipt_sha256"] = sha(folder / "receipt.json")
            r["model_launch_receipts"] += row["model_launch_receipts"]
    if a.execute:
        need(
            r["model_launch_receipts"] == 2
            and all(x["capture_tree"] == tree for x in r["arms"].values()),
            "two independent model numerics",
        )
    r["status"] = "PASS_C292_ROUTER_LOOKAHEAD_NUMERIC" if a.execute else "PREPARED_ONLY"


if __name__ == "__main__":
    raise SystemExit(bound(F["main"], campaign=campaign)())
