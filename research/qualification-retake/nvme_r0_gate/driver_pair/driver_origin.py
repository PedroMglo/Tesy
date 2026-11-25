"""Inspect a single local Flathub deployment and the original R01 loader log; no CUDA calls."""

import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
from pathlib import Path

COMMIT = "08d80c49344008a789e2084d3ed620a1d221321a9be5285153d647266c136cc4"
BRANCH = "org.freedesktop.Platform.GL.nvidia-620-70-06/x86_64/1.4"
REPO = Path("/var/lib/flatpak/repo")
DEPLOY = REPO.parent / "runtime" / BRANCH / COMMIT
LIB = DEPLOY / "files/lib"
OLD = "3220c1d499871199861f239a71e956f2b405e15b95d4736dc898f6388c7c746d"
ORDER = (
    "libcuda.so.1",
    "libnvidia-ptxjitcompiler.so.1",
    "libnvidia-nvvm70.so.4",
    "libnvidia-gpucomp.so.620.70.06",
)
MON = "libnvidia-ml.so.1"
ABSENT = "libnvcuextend.so.620.70.06"
SIGNATURE = "562702E9E3ED7EE8"


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def cmd(argv):
    return subprocess.check_output(
        argv, text=True, env=os.environ | {"LC_ALL": "C"}, timeout=15
    ).strip()


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def kernel():
    root = Path("/sys/module/nvidia")
    data = (root / "notes/.note.gnu.build-id").read_bytes()
    namesz, descsz, kind = struct.unpack_from("<III", data)
    need(
        namesz == 4 and data[12:16] == b"GNU\0" and descsz == 20 and kind == 3 and len(data) == 36,
        "module build id",
    )
    return {"build_id": data[16:].hex(), "release": (root / "version").read_text().strip()}


def deployment():
    ref = cmd(
        [
            "/usr/bin/flatpak",
            "info",
            "--system",
            "--show-ref",
            "--show-origin",
            "--show-commit",
            BRANCH,
        ]
    ).split()
    need(
        ref == ["runtime/" + BRANCH, "flathub", COMMIT]
        and (DEPLOY.parent / "active").resolve(strict=True) == DEPLOY,
        "deployment mismatch",
    )
    text = cmd(
        ["/usr/bin/ostree", "show", "--repo=" + str(REPO), "--gpg-verify-remote=flathub", COMMIT]
    )
    need(
        "Good signature from" in text and "Flathub Repo Signing Key" in text and SIGNATURE in text,
        "signed commit",
    )
    manifest = DEPLOY / "files/manifest.json"
    src = json.loads(manifest.read_bytes())["modules"][0]["sources"][1]
    need(
        src["sha256"] == "29118e3abd08c07559bcca3d9c76238d039490af0362a2e5bcfcbe7204afd4b1",
        "source installer",
    )
    return {
        "commit": COMMIT,
        "ref": ref[0],
        "origin": ref[1],
        "signature_key": SIGNATURE,
        "content_checksum": re.search(r"ContentChecksum:\s+([0-9a-f]{64})", text)[1],
        "manifest_sha256": sha(manifest),
        "installer_manifest_sha256": src["sha256"],
        "metadata_sha256": sha(DEPLOY / "metadata"),
        "deploy_sha256": sha(DEPLOY / "deploy"),
    }


def elf(path):
    info = cmd(["/usr/bin/readelf", "-d", "-n", path])
    soname = re.findall(r"\(SONAME\).*?\[([^\]]+)\]", info)
    build = re.findall(r"Build ID: (\w+)", info)
    need(len(soname) == len(build) == 1, "ELF metadata")
    return dict(
        file=path.name,
        bytes=path.stat().st_size,
        soname=soname[0],
        build_id=build[0],
        needed=re.findall(r"\(NEEDED\).*?\[([^\]]+)\]", info),
        embedded_search=re.findall(r"\((?:RPATH|RUNPATH)\).*?\[([^\]]+)\]", info),
    )


def object_info(name, rehash=False):
    path = (LIB / name).resolve(strict=True)
    need(path.parent == LIB, "outside deployment")
    row = cmd(
        ["/usr/bin/ostree", "ls", "--repo=" + str(REPO), "-C", COMMIT, "/files/lib/" + path.name]
    ).split()
    need(
        len(row) == 6
        and int(row[3]) == path.stat().st_size
        and row[5] == "/files/lib/" + path.name,
        "OSTree metadata",
    )
    obj = row[4]
    need(
        re.fullmatch("[a-f0-9]{64}", obj)
        and path.samefile(REPO / "objects" / obj[:2] / (obj[2:] + ".file")),
        "installed provider not a hardlink to the named content object",
    )
    if rehash:
        need(
            cmd(["/usr/bin/ostree", "checksum", "--ignore-xattrs", path]) == obj,
            "OSTree object digest",
        )
    meta = elf(path)
    need(meta["soname"] == name, "unexpected SONAME")
    return meta | {"ostree_file_object": obj}


def driver_name(s):
    return (
        "nvidia" in s.lower()
        or s.lower().startswith("libnv")
        or re.fullmatch(r"libcuda\.so(?:\..*)?", s) is not None
    )


def all_requests(log, pid):
    result = set()
    for line in log.splitlines():
        m = re.fullmatch(r"\s*(\d+):\s+find library=(\S+)\s+\[\d+\]; searching\s*", line)
        if m:
            need(int(m[1]) == pid, "wrong loader PID")
            result.add(m[2])
    return result


def requests(log, pid):
    return {n for n in all_requests(log, pid) if driver_name(n)}


def validate_driver_log(requested, loaded, providers):
    """Reject other resolved paths, even if their SONAME and content match."""
    need(set(providers) == set(ORDER), "frozen aliases")
    selected = {k for k, path in providers.items() if str(path) in loaded}
    other = {f for f in loaded if driver_name(Path(f).name)} - {
        str(path) for path in providers.values()
    }
    need(
        not other
        and requested <= set(ORDER) | {ABSENT}
        and requested - {ABSENT} <= selected
        and set(ORDER[:2]) <= selected,
        "foreign, unknown, or unserved NVIDIA provider",
    )
    return {
        k: {"requested": k in requested, "initialized": k in selected} for k in (*ORDER, ABSENT)
    }


def audit(old):
    receipt = json.loads((old / "receipt.json").read_bytes())
    need(sha(old / "receipt.json") == OLD and receipt["status"] == "FAIL_PRESERVED", "R01")
    phases = {}
    for k, row in receipt["phases"].items():
        path = old / (k + ".json")
        need(sha(path) == row["receipt_sha256"], "R01 phase")
        phases[k] = json.loads(path.read_bytes())
    static = old / "static-map.json"
    need(sha(static) == phases["pre"]["static_sha256"], "R01 static file")
    raw_map = json.loads(static.read_bytes())
    # Keep only SONAME, resolved basename and content digest of each startup dependency.
    linked = {
        soname: {"filename": Path(real).name, "sha256": raw_map["files"][real]["sha256"]}
        for soname, (_, real) in raw_map["links"].items()
    }
    post = phases["post"]
    pid = phases["run"]["native_pid"]
    log = old / f"loads.{pid}"
    need(
        sha(log) == post["loader_log_sha256"]
        and requests(log.read_text(), pid) == set(ORDER) | {ABSENT},
        "R01 log",
    )
    initialized = {
        Path(f).resolve(strict=True)
        for f in re.findall(r"calling init:\s*(/[^\n]+)", log.read_text())
    }
    expected = {name: (LIB / name).resolve(strict=True) for name in (*ORDER, MON)}
    # Authenticate absence by listing the directory in the signed historical commit.
    names = cmd(["/usr/bin/ostree", "ls", "--repo=" + str(REPO), COMMIT, "/files/lib"]).splitlines()
    need(
        not any("/files/lib/" + ABSENT in line for line in names)
        and not (LIB / ABSENT).exists()
        and not any(p.name == ABSENT for p in initialized),
        "optional absent query",
    )
    rows = {
        name: object_info(name, True) | {"sha256": sha(path)} for name, path in expected.items()
    }
    observed = {}
    for name in ORDER[1:3]:
        actual = (Path("/lib64") / name).resolve(strict=True)
        need(
            actual in initialized and sha(actual) == post["optional_dl_init_sha256"][actual.name],
            "R01 auxiliary mismatch",
        )
        observed[name] = elf(actual) | {
            "sha256": post["optional_dl_init_sha256"][actual.name],
            "rpm": cmd(["/usr/bin/rpm", "-qf", actual]),
            "matches_deployment_bytes": rows[name]["sha256"]
            == post["optional_dl_init_sha256"][actual.name],
        }
    need(
        expected[ORDER[0]] in initialized and not any("gpucomp" in p.name for p in initialized),
        "R01 driver provenance",
    )
    return {
        "status": "PASS_STATIC_DRIVER_ORIGIN_ONLY",
        "deployment": deployment(),
        "kernel": kernel(),
        "providers": rows,
        "r01_auxiliary_init": observed,
        "r01_receipt_sha256": OLD,
        "r01_startup": linked,
        "r01_closed_utc": receipt["closed_utc"],
        "r01_c55_sha256": receipt["c55_sha256"],
        "r01_loader_sha256": sha(log),
        "r01_all_search_names": sorted(all_requests(log.read_text(), pid)),
        "r01_all_init_names": sorted(path.name for path in initialized),
        "r01_searched": list((*ORDER, ABSENT)),
        "r01_absent_optional": ABSENT,
        "r01_gpucomp_init": False,
        "R02_KERNEL_EXECUTIONS": 0,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--r01", type=Path, required=True)
    ap.add_argument("--new-receipt", type=Path, required=True)
    a = ap.parse_args()
    with a.new_receipt.open("x") as f:
        json.dump(audit(a.r01), f, indent=2, sort_keys=True)
        f.write("\n")
