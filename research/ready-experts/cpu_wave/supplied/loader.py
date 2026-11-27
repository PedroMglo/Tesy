"""Qualify the existing data-only glibc observer against this deployment."""

import argparse
import hashlib
import importlib.util
import json
import mmap
from pathlib import Path

HERE = Path(__file__).resolve().parent
HTTP = HERE.parents[3] / "research/qualification-retake/packed_nvme_manifest/server_profile"
SOURCE = (
    HTTP
    / "verified_block/server_reserve/causal_server/http/kv_width/natural"
    / "cpu_attention/target/http/loader_data.py"
)
SOURCE_SHA = "337dba0eb5aded96966459ceafc15ab22d559f176bdf7518dbc259bcb7808c04"
DATA_SHA = "1f84460ce03f84bf2feab5341c14c689cbfe64272622de9a9e3995d755105d8e"
METHOD = "6798dfd8a9d32a235c72fdeb5dca24a46ed4e285ce21a2db4476ed34fde5bc90"
FAIL = "8030375ce881cd892d6902ac75d6131facb6184816fd7a47da10ef51f7ae98e4"


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def adapter():
    if sha(SOURCE) != SOURCE_SHA or sha(HERE / "nominal-retake.md") != METHOD:
        raise ValueError("observer or protocol changed")
    spec = importlib.util.spec_from_file_location("supplied_nominal_loader", SOURCE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # The upstream campaign stored the deployment pin as a module constant.
    # Bind the current frozen identity only in this private observer instance.
    mod.HASH = DATA_SHA
    return mod


def run_probe(failure):
    m = adapter()
    failed = json.loads(failure.read_bytes())
    m.need(
        sha(failure) == FAIL
        and failed["status"] == "FAIL_PRESERVED"
        and failed["stage"] == "6P"
        and failed["reason"] == "unexpected mapped ELF: ld.so.cache",
        "failure seal",
    )
    obs = m.LoaderCache()
    with (
        m.CACHE.open("rb") as f,
        mmap.mmap(f.fileno(), 0, flags=mmap.MAP_PRIVATE, prot=mmap.PROT_READ) as view,
    ):
        m.need(view[:20] == b"glibc-ld.so.cache1.1", "cache magic")
        maps = Path("/proc/self/maps").read_text().splitlines()
        (row,) = [r for r in maps if r.endswith(" " + str(m.CACHE)) and r.split()[1] == "r--p"]
        libc = next(r for r in maps if "/libc.so." in r and r.split()[1] == "r-xp")
        lib = str(Path(libc.split(maxsplit=5)[5]).resolve(strict=True))
        keys = {lib: m.AU["reference_key"](lib, m.AU["identity"](lib))}

        def audit(rows):
            return m.AU["check_maps"](obs.providers("\n".join(rows)), {lib}, keys)

        m.need(audit([libc, row]) == audit([libc]) == {lib}, "ELF census")
        fields = row.split(maxsplit=5)
        lo, hi = fields[0].split("-")
        bad = {"duplicate": [row, row]}
        for name, i, v in (
            ("inode", 4, str(int(fields[4]) + 1)),
            ("device", 3, "00:00"),
            ("offset", 2, "1000"),
            ("size", 0, f"{lo}-{int(hi, 16) + mmap.PAGESIZE:x}"),
            ("execute", 1, "r-xp"),
            ("write", 1, "rw-p"),
            ("shared", 1, "r--s"),
            ("path", 5, "/tmp/foreign/ld.so.cache"),
            ("deleted", 5, str(m.CACHE) + " (deleted)"),
        ):
            other = fields.copy()
            other[i] = v
            bad[name] = [" ".join(other)]
        for name, rows in bad.items():
            try:
                audit([libc, *rows])
            except (ValueError, FileNotFoundError):
                continue
            raise ValueError("accepted mutated observer input " + name)
    return dict(
        status="GO_DATA_OBSERVER",
        failed_sha256=FAIL,
        protocol_sha256=METHOD,
        observer_sha256=SOURCE_SHA,
        cache=obs.receipt(),
        rejected=sorted(bad),
        model_starts=0,
    )


def checked(path, digest):
    m = adapter()
    obs = m.LoaderCache()
    rec = json.loads(path.read_bytes())
    m.need(
        sha(path) == digest
        and rec["status"] == "GO_DATA_OBSERVER"
        and rec["failed_sha256"] == FAIL
        and rec["protocol_sha256"] == METHOD
        and rec["observer_sha256"] == SOURCE_SHA
        and obs.receipt() == dict(rec["cache"], observed_cuts=0),
        "deployment differs from probe",
    )
    return obs


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--failure", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = run_probe(a.failure)
    except Exception as exc:
        result = dict(status="FAIL_PRESERVED", reason=str(exc))
    with (a.new_output_dir / "receipt.json").open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(result["status"], result.get("reason", ""))
    raise SystemExit(result["status"] != "GO_DATA_OBSERVER")
