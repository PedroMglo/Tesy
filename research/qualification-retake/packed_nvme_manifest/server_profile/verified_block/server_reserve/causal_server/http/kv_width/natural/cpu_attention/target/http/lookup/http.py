"""Attach the individually verified proposer to C281 and preserve its target closure."""

import os
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
S = run_path(str(HERE.parent / "serve.py"))
G, H, sha, need, save = (S[k] for k in ("G", "H", "sha", "need", "save"))
METHOD = "86d8ad309e28b81ce12d193e08343fe14beaa579d7df894d2acd4187cad4e604"
REVIEW = "6882001e2807aa25ddc92b94829b696f3f5b77be373803f01d677421fe57c1ff"
MODES = {"FILTER": "ON", "FIXED": "ON", "SERIAL": "OFF", "R": "R"}


class Runtime(S["Runtime"]):
    def __init__(self, a, root, mode):
        H["SESSION"].require_session_id(a.unit)
        super().__init__(a, root, mode)
        reviewed = G["read"](HERE / "result.json", REVIEW)
        pin = sha(a.lookup_run / "result.json")
        need(
            pin in reviewed["input_sha256"][1:]
            and reviewed["status"] == "GO_NATIVE_CONTEXT_FILTER_ONLY",
            "qualified proposer",
        )
        image = G["read"](a.lookup_run / "result.json", pin)
        tag = "ON" if a.mode == "FILTER" else "OFF"
        record = dict(
            arm=a.mode, numerical_mode=mode, lookup_build_sha256=pin, review_sha256=REVIEW
        )
        if a.mode != "R":
            soname = "libllama-common.so.0"
            old = self.closure[soname]
            native = a.lookup_run / "FILTER" / soname
            path = str(native.resolve(strict=True))
            sig = reviewed["images"]["FILTER"]["ELF_sha256"]
            need(
                str(native) == path
                and sha(native) == sig == image["images"]["FILTER"]["ELF_sha256"]
                and old["sha256"] == image["images"]["CONTROL"]["ELF_sha256"],
                "original and filtered common ELF",
            )
            ctl = self.auth
            for table in (ctl.stats, ctl.files, ctl.keys):
                del table[old["file"]]
            ctl.stats[path] = H["AU"]["identity"](path)
            ctl.files[path] = sig
            ctl.keys[path] = H["AU"]["reference_key"](path, ctl.stats[path])
            ctl.allowed = set(ctl.files)
            ctl.initial = (ctl.initial - {old["file"]}) | {path}
            ctl.search = str(native.parent) + os.pathsep + ctl.search
            self.closure[soname] = dict(file=path, sha256=sig)
            self.dso = self.dso | {soname: dict(path=path, sha256=sig)}
            self.loader = self.loader | dict(LD_LIBRARY_PATH=ctl.search)
            self.native = self.native | dict(dso=self.dso)
            if mode == "ON":
                self.plan_sha256 = reviewed["raw_digests"][tag]
                self.plan = G["read"](a.lookup_run / tag / "proposals.json", self.plan_sha256)
                for turn in ("T1", "T2"):
                    sites = [x["at"] for x in self.plan[turn] if x["proposal"]]
                    need(sites == reviewed["arms"][tag][turn]["positions"], "actual dispatch sites")
            if a.mode == "FILTER":
                self.expected = self.expected | {"TESY_NGRAM_PREVIOUS_TOKEN": "1"}
            record.update(common_path=path, common_sha256=sig, lookup_enabled=a.mode == "FILTER")
        record["active_schedule_sha256"] = getattr(self, "plan_sha256", H["PLAN_PIN"])
        save(root / "filter-provider.json", record)
        self.recheck()

    def bind_c270(self, a, cfg, digest):
        # The numerical client does not link the server proposer. Its full physical
        # startup and graph-provider checks remain in the inherited method.
        if self.mode != "R":
            need(
                not any(
                    name.startswith("libllama-common")
                    for name in cfg["pinned"]["startup_dso_sha256"]
                ),
                "disjoint numerical provider set",
            )
        super().bind_c270(a, cfg, digest)


if __name__ == "__main__":
    raise SystemExit(
        S["main"](
            runtime=Runtime,
            modes=MODES,
            protocol=HERE / "http-protocol.md",
            method=METHOD,
            program=__file__,
            extra_paths=("lookup-run",),
        )
    )
