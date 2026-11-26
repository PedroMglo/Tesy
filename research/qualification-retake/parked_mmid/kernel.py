"""Generate an opt-in patch for the authenticated C269 CPU translation unit."""

import argparse
import hashlib
from pathlib import Path

ORIGINAL = "bda1c2c81077d89813c3b4776079a5ddf65eaf28bf1e33338473818cc56831f5"
FUNCTION = "static void ggml_compute_forward_mul_mat_id(\n"
INSERT_BEFORE = "    // row groups\n"
HELPER = """\
#ifdef TESY_C47_CPU_SKIP_PARKED
// This only suppresses work for MXFP4 CPU prefill when every logical ID in
// this node is the C47 parking sentinel. Gate/up may broadcast one activation
// row to multiple ranks. The first ID alone cannot determine eligibility.
static bool tesy_all_parked_mxfp4_prefill(const struct ggml_tensor * ids) {
    if (ids->ne[1] <= 1) {
        return false;
    }
    const char * mode = getenv("TESY_CPU_MMX_ALL_PARKED");
    if (mode == NULL || strcmp(mode, "0") == 0) {
        return false;
    }
    if (strcmp(mode, "1") != 0) {
        GGML_ABORT("TESY_CPU_MMX_ALL_PARKED must be absent, 0 or 1");
    }
    for (int64_t token = 0; token < ids->ne[1]; ++token) {
        for (int64_t rank = 0; rank < ids->ne[0]; ++rank) {
            int32_t expert;
            const char * item = (const char *) ids->data + token*ids->nb[1] + rank*ids->nb[0];
            memcpy(&expert, item, sizeof(expert));
            if (expert != -1) {
                return false;
            }
        }
    }
    return true;
}
#endif

"""
SHORTCUT = """\
#ifdef TESY_C47_CPU_SKIP_PARKED
    if (type == GGML_TYPE_MXFP4 && src1->type == GGML_TYPE_F32 && dst->type == GGML_TYPE_F32 &&
            tesy_all_parked_mxfp4_prefill(ids)) {
        // R0 writes +0 to each parked F32 result. Preserve row gaps; each
        // thread owns distinct output rows. All threads take the same branch.
        const int64_t ranks = ids->ne[0];
        for (int64_t row = ith; row < ranks*ids->ne[1]; row += nth) {
            char * out = (char *) dst->data + (row/ranks)*nb2 + (row%ranks)*nb1;
            memset(out, 0, ne01*sizeof(float));
        }
        return;
    }
#endif

"""


def materialize(source: Path, dest: Path) -> str:
    original = source.read_bytes()
    if hashlib.sha256(original).hexdigest() != ORIGINAL:
        raise ValueError("wrong C269 ggml-cpu.c")
    code = original.decode("utf-8")
    if code.count(FUNCTION) != 1:
        raise ValueError("MMID function anchor")
    prefix, function = code.split(FUNCTION)
    if function.index(INSERT_BEFORE) > function.index("ggml_from_float_t") + 1500:
        raise ValueError("workspace anchor")
    function = function.replace(INSERT_BEFORE, SHORTCUT + INSERT_BEFORE, 1)
    generated = (prefix + HELPER + FUNCTION + function).encode("utf-8")
    with dest.open("xb") as f:
        f.write(generated)
    return hashlib.sha256(generated).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--new-source", type=Path, required=True)
    args = parser.parse_args()
    print(materialize(args.source, args.new_source))


if __name__ == "__main__":
    main()
