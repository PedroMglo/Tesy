"""Authenticate the data-only glibc loader-cache mapping alongside the unchanged ELF census."""

import argparse
import mmap
import os
import stat
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
CUT = run_path(str(HERE.parent / "family.py"))
G, F, sha, need, save = (CUT[k] for k in ("G", "F", "sha", "need", "save"))
AU = F["S"]["N"]["AU"]
CACHE = Path("/etc/ld.so.cache")
HASH = "6b735fd19e8fcb2d9f5b6e0523a260ccf8a497e5210d998e9acbcbd29baef21c"
METHOD = "b097c3dce47106464286ed576b89577559370a35d6c5bee4867d060dd18a30cd"
FAILED = "f1af9bfbd6d6dd9d3b69eb4971cf174e054ff92f5db3d724fc94917d03160b9b"


class LoaderCache:
    def __init__(self):
        st = CACHE.lstat()
        need(
            CACHE.resolve(strict=True) == CACHE
            and stat.S_ISREG(st.st_mode)
            and st.st_uid == 0
            and not st.st_mode & 0o022
            and sha(CACHE) == HASH,
            "glibc cache identity",
        )
        with CACHE.open("rb") as f:
            need(f.read(20) == b"glibc-ld.so.cache1.1", "glibc cache format")
        info = AU["identity"](str(CACHE))
        self.key = AU["reference_key"](str(CACHE), info)
        self.info = info
        self.length = ((info["size"] + mmap.PAGESIZE - 1) // mmap.PAGESIZE) * mmap.PAGESIZE
        self.cuts = 0
        self.check()

    def check(self):
        need(AU["identity"](str(CACHE)) == self.info, "loader data file changed")

    def providers(self, maps):
        kept = []
        found = 0
        for row in maps.splitlines():
            fields = row.split(maxsplit=5)
            if len(fields) != 6 or fields[5] != str(CACHE):
                kept.append(row)
                continue
            lo, hi = (int(v, 16) for v in fields[0].split("-"))
            need(
                found == 0
                and fields[1] == "r--p"
                and int(fields[2], 16) == 0
                and hi - lo == self.length
                and AU["mapping_key"](fields) == self.key,
                "loader data VMA",
            )
            self.check()
            found += 1
        self.cuts += found
        return "\n".join(kept)

    def receipt(self):
        self.check()
        need(sha(CACHE) == HASH, "loader data final SHA")
        return dict(
            path=str(CACHE),
            sha256=HASH,
            identity=self.info,
            VMA_key=list(self.key),
            mapped_length=self.length,
            observed_cuts=self.cuts,
        )


def probe(a, out):
    h, tree = G["tree"](G["REPO"])
    need(h == a.commit and sha(HERE / "loader_protocol.md") == METHOD, "frozen loader study")
    failed = G["read"](a.failed / "receipt.json", FAILED)
    need(
        failed["status"] == "FAIL_PRESERVED"
        and failed["error"] == "ValueError: unexpected mapped ELF: ld.so.cache"
        and failed["model_starts"] == 1
        and failed["http_requests"] == 0,
        "preserved failed start",
    )
    for k, v in failed["files"].items():
        need(sha(a.failed / k) == v, "raw failure evidence")
    cap = next((a.failed / "OFF/raw").glob("*.capture"))
    launch = F["read"](next((a.failed / "OFF/raw").glob("*.launch.json")))
    pid = launch["process_identity"]["pid"]
    log = (a.failed / "OFF/raw" / ("loader." + str(pid))).read_bytes()
    need(
        not list(cap.iterdir())
        and b"search cache=/etc/ld.so.cache" in log
        and "status=15/TERM" in (a.failed / "OFF/scope.log").read_text(),
        "aborted before numerical capture",
    )
    cache = LoaderCache()
    with (
        CACHE.open("rb") as stream,
        mmap.mmap(stream.fileno(), 0, flags=mmap.MAP_PRIVATE, prot=mmap.PROT_READ) as view,
    ):
        need(view[:20] == b"glibc-ld.so.cache1.1", "observed data mapping")
        maps = Path("/proc/self/maps").read_text().splitlines()
        rows = [s for s in maps if s.endswith(" " + str(CACHE)) and s.split()[1] == "r--p"]
        need(len(rows) == 1, "one real passive data mapping")
        row = rows[0]
        lib = next(s for s in maps if "/libc.so." in s and s.split()[1] == "r-xp")
        fields = lib.split(maxsplit=5)
        path = str(Path(fields[5]).resolve(strict=True))
        keys = {path: AU["reference_key"](path, AU["identity"](path))}

        def audit(lines, prepared):
            data = "\n".join(lines)
            return AU["check_maps"](cache.providers(data) if prepared else data, {path}, keys)

        def reject(lines, prepared=True):
            try:
                audit(lines, prepared)
            except (ValueError, FileNotFoundError):
                return True
            raise ValueError("invalid data mapping passed")

        need(reject([lib, row], False), "historical counterexample")
        need(audit([lib, row], True) == audit([lib], False) == {path}, "same real ELF census")
        raw = row.split(maxsplit=5)
        variants = {}
        end = int(raw[0].split("-")[1], 16)
        for name, i, val in (
            ("path", 5, "/run/tesy-wrong-dir/ld.so.cache"),
            ("inode", 4, str(int(raw[4]) + 1)),
            ("device", 3, "00:00"),
            ("length", 0, raw[0].split("-")[0] + "-" + format(end + mmap.PAGESIZE, "x")),
            ("offset", 2, "00001000"),
            ("execute", 1, "r-xp"),
            ("write", 1, "rw-p"),
            ("shared", 1, "r--s"),
            ("deleted", 5, str(CACHE) + " (deleted)"),
        ):
            changed = raw.copy()
            changed[i] = val
            variants[name] = reject([lib, " ".join(changed)])
        variants["duplicate"] = reject([lib, row, row])
        (out / "observed-maps.txt").write_text(lib + "\n" + row + "\n")
    return dict(
        status="GO_LOADER_DATA_OBSERVER_ONLY",
        commit=h,
        tree=tree,
        protocol_sha256=METHOD,
        failed_sha256=FAILED,
        failed_gpu_start=True,
        failed_completed_distributions=0,
        older_receipt_missing_VMA_fields=True,
        cache=cache.receipt(),
        canonical_elf=path,
        rejected=variants,
        model_starts=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--failed", type=Path, required=True)
    p.add_argument("--commit", required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    try:
        r = probe(a, out)
    except Exception as exc:
        r = dict(
            status="FAIL_PRESERVED",
            commit=a.commit,
            protocol_sha256=METHOD,
            error=f"{type(exc).__name__}: {exc}",
        )
    r["files"] = {p.name: sha(p) for p in out.iterdir() if p.is_file()}
    save(out / "receipt.json", r)
    print(r["status"], r.get("error", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
