"""Compare the complete, independently identified C291 ELFs across the toolchain update."""

import hashlib
import struct

ELF = struct.Struct("<16sHHIQQQIHHHHHH")
SECTION = struct.Struct("<IIQQQQIIQQ")
ALLOWED = {".comment", ".note.gnu.build-id"}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def layout(blob):
    head = ELF.unpack_from(blob)
    require(head[0][:6] == b"\x7fELF\x02\x01" and head[11] == SECTION.size, "ELF64 LE")
    sections = [SECTION.unpack_from(blob, head[6] + i * head[11]) for i in range(head[12])]
    names = sections[head[13]]
    table = blob[names[4] : names[4] + names[5]]
    rows = {}
    for row in sections:
        name = table[row[0] :].split(b"\0", 1)[0].decode()
        require(name not in rows, "duplicate section")
        # SHT_NOBITS describes memory and consumes no bytes in the ELF.
        data = b"" if row[1] == 8 else blob[row[4] : row[4] + row[5]]
        rows[name] = (row, data)
    programs = blob[head[5] : head[5] + head[9] * head[10]]
    return head, programs, rows


def compare(old, current):
    left, right = layout(old.read_bytes()), layout(current.read_bytes())
    a, b = left[0], right[0]
    require(a[:6] + a[7:] == b[:6] + b[7:] and left[1] == right[1], "ELF/program header")
    x, y = left[2], right[2]
    require(list(x) == list(y) and ALLOWED <= x.keys(), "section names/order")
    cutoff = x[".comment"][0][4]
    differences = {}
    for name in x:
        hx, dx = x[name]
        hy, dy = y[name]
        for i, (v, w) in enumerate(zip(hx, hy, strict=True)):
            require(
                v == w or (i == 4 and hx[4] > cutoff) or (name == ".comment" and i == 5),
                "section layout " + name,
            )
        if dx != dy:
            require(name in ALLOWED, "section payload " + name)
            differences[name] = [
                {"bytes": len(d), "sha256": hashlib.sha256(d).hexdigest()} for d in (dx, dy)
            ]
    require(differences.keys() == ALLOWED, "expected both distinct metadata sections")
    return {
        "program_headers_identical": a[10],
        "sections": len(x),
        "unchanged_section_payloads": len(x) - len(differences),
        "different_section_payloads": differences,
    }
