"""Run the frozen tiny_loader arms with a measured, independently bounded resident scope."""

import argparse
import importlib.util
import json
import resource
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("tiny_ik_driver", HERE / "run.py")
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def apply():
    resource.setrlimit(resource.RLIMIT_AS, (768 << 20, 768 << 20))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))


def values(root):
    return {
        k: int((root / k).read_text())
        for k in (
            "memory.max",
            "memory.swap.max",
            "memory.current",
            "memory.peak",
            "memory.swap.peak",
        )
    } | {
        "events": {
            k: int(n)
            for k, n in (line.split() for line in (root / "memory.events").read_text().splitlines())
        }
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "objects", "build", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--build-sha256", required=True)
    p.add_argument("--scope", required=True)
    a = p.parse_args()
    a.mode = "run"
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    result = {
        "virtual_limit_bytes": 768 << 20,
        "resident_limit_bytes": 150 << 20,
        "r01_sha256": "4cace6b6464f09816ce2809ec3a8babb50d9fb8734758538b8acc7a2f912dd9d",
        "controller_sha256": driver.sha(Path(__file__)),
        "supplement_sha256": driver.sha(HERE / "resident.md"),
    }
    root = None
    try:
        entry = Path("/proc/self/cgroup").read_text().strip().split("::", 1)
        driver.need(
            entry[0] == "0"
            and a.scope.startswith("tesy-ik-tiny-")
            and Path(entry[1]).name == a.scope + ".scope",
            "expected transient scope",
        )
        root = Path("/sys/fs/cgroup") / entry[1].lstrip("/")
        before = values(root)
        result.update(scope=root.name, cgroup_before=before)
        driver.need(
            before["memory.max"] == 150 << 20
            and before["memory.swap.max"] == 0
            and before["memory.swap.peak"] == 0,
            "scope resource envelope",
        )
        driver.bounded = apply
        status = driver.run(a, out, result)
        after = values(root)
        result["cgroup_after"] = after
        driver.need(
            after["memory.peak"] <= 150 << 20
            and after["memory.swap.peak"] == 0
            and after["events"] == before["events"],
            "resource event or cap",
        )
        result["status"] = status
    except Exception as e:
        if root is not None:
            result["cgroup_after"] = values(root)
        result.update(status="FAIL_PRESERVED", error=str(e))
    with (out / ".receipt.tmp").open("x") as h:
        json.dump(result, h, sort_keys=True, indent=2)
        h.write("\n")
    (out / ".receipt.tmp").rename(out / "receipt.json")
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
