"""Deliver the fixed workload from native C290 offsets on its sealed NVMe copy."""

import argparse
import hashlib
import json
import os
import re
import signal
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
SINK = HERE.parent / "t1_native_sink"
PACK = "f17e9fbf6f6aed1ad60ca7da3431c5156a946d2e0bf119722afc1f934cbc6b11"
INDEX = "f8961dcdaa58aa7774e63150b76d69add0dd080181493838528c8f36de543a57"
READBACK = "54273ebffab1294357932b5c4ee6823be7cb9d9d7420b5582b7294c744b658a0"
RUNTIME = "4ff6825ccf8d18498c1f2323fd44eacd57c3a8d3278e3aab3adb973a409dd48b"
SLICE_REF = "c70cb5b267cc26877f8d353c8cdb27c6f7334b392be6c9983ddbbad61e6f57fe"
SIZE, STRIDE, WINDOW = 61_096_329_216, 13_258_752, 13_221_888
FIELDS = ("dev", "ino", "size", "mtime_ns", "ctime_ns")


def need(ok, message):
    if not ok:
        raise ValueError(message)


def read(path, digest):
    data = path.read_bytes()
    need(not path.is_symlink() and hashlib.sha256(data).hexdigest() == digest, "seal: " + path.name)
    return json.loads(data)


def validate_placement(row):
    need(
        row["status"] == "PASS_NVME_C290_FULL_PACK_PLACEMENT"
        and row["size_bytes"]
        == SIZE
        == row["destination_stat"]["size"]
        == row["source_stat"]["size"]
        and row["source_sha256"] == row["destination_sha256"] == PACK
        and row["index_sha256"] == INDEX
        and row["readback_sha256"] == READBACK
        and row["runtime_manifest_sha256"] == RUNTIME
        and row["binary_launches"] == 0
        and row["source_transport"] == "usb"
        and row["destination_transport"] == "nvme"
        and re.fullmatch("[0-9a-f]{40}", row["commit"])
        and re.fullmatch("[0-9a-f]{40}", row["tree"]),
        "full-pack placement authority",
    )
    d = [row["destination_stat"][k] for k in FIELDS]
    s = [row["source_stat"][k] for k in FIELDS]
    need(
        all(type(x) is int and x > 0 for x in d + s) and d[:2] != s[:2],
        "distinct regular-file identities",
    )
    return d


def integral_entries(entries):
    result = {}
    for i, (key, (compact, item)) in enumerate(entries.items()):
        layer, expert = key
        identity = (item["layer"], item["expert"])
        off = item["pack_offset"]
        need(
            key == identity
            and 0 <= layer < 36
            and 0 <= expert < 128
            and compact == i * WINDOW
            and off == (128 * layer + expert) * STRIDE
            and off % 4096 == 0
            and off + WINDOW <= SIZE,
            "C290 full record offset",
        )
        result[key] = (off, item)
    return result


def offsets_digest(entries):
    return hashlib.sha256(
        json.dumps([[*k, off] for k, (off, _) in entries.items()], separators=(",", ":")).encode()
    ).hexdigest()


class FullPack:
    def __init__(self, receipt, digest, *, offline=False):
        row = read(receipt, digest)
        self.stat = validate_placement(row)
        self.path = Path(row["destination"])
        need(self.path.is_absolute(), "absolute placement destination")
        if not offline:
            need(
                self.path.resolve(strict=True) == self.path
                and self.path.is_file()
                and not self.path.is_symlink()
                and not (self.path.stat().st_mode & 0o222),
                "sealed read-only local destination",
            )
        reference = read(SINK / "evidence/receipt.json", SLICE_REF)
        need(
            reference["status"] == "GO_MANAGER_FIXTURE_ONLY"
            and reference["distinct_consumer_components"] == 87,
            "published compact-layout reference",
        )
        self.evidence = dict(
            placement_sha256=digest,
            full_pack_sha256=PACK,
            full_pack_size=SIZE,
            placement_commit=row["commit"],
            placement_tree=row["tree"],
            placement_index_sha256=INDEX,
            placement_readback_sha256=READBACK,
            runtime_manifest_sha256=RUNTIME,
            compact_reference_sha256=SLICE_REF,
        )

    def bind(self, plan, seal, entries):
        expected = seal["inputs"]
        need(
            plan["index"] == expected["index"] == INDEX
            and plan["readback"] == expected["readback"] == READBACK
            and plan["journal"] == expected["journal"]
            and plan["causal"] == expected["causal"]
            and len(entries) == 29,
            "same weights, causal cutoff and reference indices",
        )
        resolved = integral_entries(entries)
        self.evidence["offsets_sha256"] = offsets_digest(resolved)
        self.evidence["journal_sha256"] = expected["journal"]
        self.evidence["causal_sha256"] = expected["causal"]
        return resolved


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("unit", "commit", "c55-sha256", "placement-sha256", "first-sha256"):
        p.add_argument("--" + k, required=k != "first-sha256")
    for k in ("model", "placement", "plan", "c55", "ram-dir", "map", "first-dir", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=k != "first-dir")
    p.add_argument("--arm", type=int, choices=(1, 2), required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir
    out.mkdir(mode=0o700)

    def alarm(*_):
        raise TimeoutError("full-pack arm deadline")

    signal.signal(signal.SIGALRM, alarm)
    signal.alarm(225)
    result = {}
    try:
        need(
            (a.arm == 1) == (a.first_dir is None) == (a.first_sha256 is None),
            "independent process chain",
        )
        pack = FullPack(a.placement, a.placement_sha256)
        run_path(str(SINK / "measure.py"))["execute"](a, result, out, full_pack=pack)
    except Exception as exc:
        result.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    finally:
        signal.alarm(0)
        with (out / "receipt.json").open("x") as f:
            json.dump(result, f, sort_keys=True, indent=2, allow_nan=False)
            f.write("\n")
    print(result["status"], result.get("reason", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
