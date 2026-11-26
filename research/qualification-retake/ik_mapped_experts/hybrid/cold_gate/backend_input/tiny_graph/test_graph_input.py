"""Independent, deliberately small journals for the physical-to-logical source join."""

from pathlib import Path
from runpy import run_path

import pytest

A = run_path(str(Path(__file__).with_name("grade.py")))


def example(folder, mode):
    tiny = folder / "example.gguf"
    tiny.write_bytes(b"fixture")
    s = tiny.stat()
    major, minor = A["mapped_device"](tiny)
    model, arena, dst = 0x10000000, 0x20000000, 0x30000000
    (folder / "maps").write_text(
        f"{model:x}-{model + 3390592:x} r--s 00000000 "
        f"{major:x}:{minor:x} "
        f"{s.st_ino} {tiny}\n{arena:x}-{arena + (1 << 20):x} rw-p 00000000 00:00 0\n"
    )
    lines = []
    last = ticket = 0
    for gen, (phase, layer, fills) in enumerate(((3, 0, 5), (3, 1, 5), (4, 0, 1), (4, 1, 0)), 1):
        ranks = ",".join(["0,1,2,3"] * (32 if phase == 3 else 1))
        lines.extend(
            [
                f"ROUTE {phase} ffn_moe_topk-{layer} {ranks}",
                f"BANK_GET {phase} {gen} 22 44 {512 if phase == 3 else 16}",
                f"BANK_FENCE {phase} {gen} 22 55 {last} {ranks}",
            ]
        )
        cursor = last = 0
        if not fills:
            continue
        for role in A["G"]["ROLES"]:
            ticket += 1
            off = A["G"]["WEIGHTS"][layer, role]
            n = fills * A["G"]["SLAB"]
            orig = model + off
            head = cursor + off % 4096
            eff, ef = (orig, off) if mode == "DIRECT" else (arena + head, -1)
            cursor = ((head + n + 4095) // 4096) * 4096
            lines.extend(
                [
                    f"SET {phase} {ticket} 0 async moe_cache.blk.0.ffn_{role}_exps.weight "
                    f"{dst} 0 {n} {orig} {off}",
                    f"BANK_SOURCE {phase} {ticket} {gen} 22 {layer} {orig} {off} {eff} {ef} {n}",
                    f"COPY {phase} {ticket} async 1 {dst} {eff} {n} {ef} 0",
                ]
            )
            last += 1
    return lines + ["BANK_END 4 0", "STATUS COMPLETED_TINY_HYBRID_CLIENT"], tiny


@pytest.mark.parametrize("mode", ["DIRECT", "PREAD_RANDOM"])
def test_physical_sources(tmp_path, mode):
    lines, tiny = example(tmp_path, mode)
    logical, receipt = A["audit"]("\n".join(lines), mode, tmp_path, tiny)
    assert receipt["bank_sets"] == receipt["physical_copies"] == 9
    assert receipt["id_fences"] == 4
    assert all(int(w[7]) >= 0 for w in A["G"]["records"](logical, "COPY"))


def test_require_device_of_authenticated_mapping(tmp_path, monkeypatch):
    lines, tiny = example(tmp_path, "DIRECT")
    raw = "\n".join(lines)
    vm = tmp_path / "maps"
    rows = vm.read_text().splitlines()
    words = rows[0].split()
    words[3] = "0a:ee"
    vm.write_text(" ".join(words) + "\n" + rows[1] + "\n")
    monkeypatch.setitem(A["audit"].__globals__, "mapped_device", lambda _: (10, 238))
    assert A["audit"](raw, "DIRECT", tmp_path, tiny)[1]["bank_sets"] == 9
    monkeypatch.setitem(A["audit"].__globals__, "mapped_device", lambda _: (10, 239))
    with pytest.raises(ValueError, match="original GGUF VMA"):
        A["audit"](raw, "DIRECT", tmp_path, tiny)


@pytest.mark.parametrize(
    "fault",
    [
        "missing_source",
        "wrong_pointer",
        "late_fence",
        "duplicate_copy",
        "wrong_file",
        "wrong_owner",
        "unbound_scratch",
        "copy_before_set",
        "wrong_direction",
        "missing_bytes",
        "reused_address",
        "early_cleanup",
        "wrong_mode",
        "different_ids",
    ],
)
def test_journal_faults(tmp_path, fault):
    lines, tiny = example(tmp_path, "PREAD_RANDOM")
    copy = next(i for i, s in enumerate(lines) if s.startswith("COPY "))
    source = copy - 1
    mode = "PREAD_RANDOM"
    if fault in ("wrong_pointer", "wrong_owner", "wrong_direction", "missing_bytes", "wrong_file"):
        field = dict(
            wrong_pointer=6, wrong_owner=2, wrong_direction=4, missing_bytes=7, wrong_file=8
        )[fault]
        w = lines[copy].split()
        w[field] = str(int(w[field]) + 1)
        lines[copy] = " ".join(w)
    elif fault == "missing_source":
        del lines[source]
    elif fault == "late_fence":
        lines.insert(copy, lines.pop(2))
    elif fault == "duplicate_copy":
        lines.insert(copy, lines[copy])
    elif fault == "unbound_scratch":
        lines.insert(copy, lines[copy].replace("COPY 3 1 ", "COPY 3 0 "))
    elif fault == "copy_before_set":
        lines.insert(source - 1, lines[copy])
    elif fault == "reused_address":
        w = lines[source + 3].split()
        w[8] = lines[source].split()[8]
        lines[source + 3] = " ".join(w)
    elif fault == "early_cleanup":
        lines.insert(0, lines.pop(-2))
    elif fault == "wrong_mode":
        mode = "DIRECT"
    elif fault == "different_ids":
        lines[2] = lines[2].replace("0,1,2,3", "1,0,2,3")
    with pytest.raises(ValueError):
        A["audit"]("\n".join(lines), mode, tmp_path, tiny)
