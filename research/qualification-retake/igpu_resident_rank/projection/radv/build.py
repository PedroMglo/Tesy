"""Build the bounded RADV MMVQ projection with the qualified C269 activation module."""

import argparse
import os
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
RHS = HERE.parents[1] / "rhs_device"
PRIOR = run_path(RHS / "run.py")
BASE = PRIOR["BASE"]
sha, need, save = (BASE[k] for k in ("sha", "need", "save"))
PROTO = "ddbd101d1aabbd18a1e369b1f5f73efb11a61042ffc57226da2f9fc3a7b51e5b"
HEADER_COMMIT = "1dace16d8044758d32736eb59802d171970e9448"
HEADERS = {
    "vulkan_core.h": "d5d48fa8fedf9804e1dcf17af4c1e177ba20bbd3c38f7f619b8cf378feb7c332",
    "vk_platform.h": "6103e0dd164567caaf887a18ea0f8c267e227ad4afaf94437bd9919b8d50d050",
}
CRYPTO = Path("/usr/lib64/libcrypto.so.3")
CRYPTO_SHA = "695648ac8dc5e6a2b70e5e72399940de0f84bf24fddb7dd18949ba40bc575c72"


def replace(source, before, after):
    need(source.count(before) == 1, "unique source span: " + before[:45])
    return source.replace(before, after)


def pin():
    need(sha(HERE / "protocol.md") == PROTO, "projection protocol")
    need(
        sha(RHS / "evidence/receipt.json")
        == "472fa699385b57fc56df08c48264f0bb39ba8731365c3adc6b581858e2e45edd",
        "RHS prior",
    )
    need(sha(CRYPTO) == CRYPTO_SHA, "libcrypto")
    return dict(
        deployment=PRIOR["seals"](),
        protocol=PROTO,
        sources={
            n: sha(HERE / n)
            for n in ("build.py", "compile.py", "projection.inc", "dot-features.inc", "run.py")
        },
    )


def prepare_native(out):
    PRIOR["prepare_host"](out)
    helper = out / "host-functions.inc"
    src = replace(
        helper.read_text(),
        "get, bool dedicated) {",
        "get, bool dedicated, size_t requested=payload) {",
    )
    src = replace(src, "cb.size=rounded(payload,", "cb.size=rounded(requested,")
    helper.write_text(replace(src, "v.bytes <= 16u<<20", "v.bytes <= 24u<<20"))
    native = RHS / "dispatch.cpp"
    need(
        sha(native) == "22ba8c88058803f5368a88194ce5347ae9f93b5fa07f15a1aa337bbfcad6e774",
        "dispatch parent",
    )
    src = replace(
        native.read_text(),
        "void compute(char **args) {",
        '#include "projection.inc"\nvoid compute(char **args) {',
    )
    flags = '#include "dot-features.inc"'
    src = replace(
        src,
        "    VkPhysicalDeviceFeatures core{};",
        flags + "\n    VkPhysicalDeviceFeatures core{};",
    )
    src = replace(
        src,
        "eSize.computeFullSubgroups=sub;",
        "eSize.computeFullSubgroups=sub; eSize.subgroupSizeControl=VK_TRUE; eSize.pNext=&dotf;",
    )
    src = replace(
        src,
        "e12.shaderInt8=VK_TRUE;",
        "e12.storageBuffer8BitAccess=VK_TRUE; e12.shaderInt8=VK_TRUE;",
    )
    src = replace(
        src,
        'std::array<const char *,2> extNames{"VK_EXT_external_memory_host",'
        '"VK_EXT_subgroup_size_control"};',
        'std::array<const char *,3> extNames{"VK_EXT_external_memory_host",'
        '"VK_EXT_subgroup_size_control","VK_KHR_shader_integer_dot_product"};',
    )
    src = replace(src, "dc.enabledExtensionCount=sub ? 2 : 1;", "dc.enabledExtensionCount=3;")
    src = replace(
        src,
        "    providers();\n    vkDestroyFence",
        "    project({gpu,dev,queue,q,mp,hp.minImportedHostPointerAlignment,get,"
        "bool(features & VK_EXTERNAL_MEMORY_FEATURE_DEDICATED_ONLY_BIT),group}, dst, args);\n"
        "    providers();\n    vkDestroyFence",
    )
    src = replace(src, "argc==5", "argc==9")
    src = replace(src, "PASS_RHS_DISPATCH", "PASS_RADV_PROJECTION_DISPATCH")
    (out / "dispatch.cpp").write_text(src)


def build(backend, headers, out):
    need(
        all(sha(headers / "vulkan" / n) == h for n, h in HEADERS.items()), "projection header pins"
    )
    modules = run_path(HERE / "compile.py")["build"](backend, out)
    need(
        modules["mode"] == "mmvq"
        and modules["module_sha256"]
        == "844058d5a5c41ea251cd3721e77878036a0d34e8d8a2db8fe64a8e34864cffba",
        "qualified MMVQ build",
    )
    rhs = run_path(RHS / "compile_shader.py")["compile_modules"](backend, out)
    need(
        rhs["modules"]["subgroup"]["sha256"]
        == "a988ec4090dca42f89a13de2ce43a69c376a0e79919e6f56875d4b1e0ab1ad25",
        "physical RHS module",
    )
    prepare_native(out)
    args = [
        str(BASE["CXX"]),
        "-std=c++17",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-Wno-missing-field-initializers",
        "-I",
        str(headers),
        "-I",
        str(HERE),
        "-I",
        str(out),
        str(out / "dispatch.cpp"),
        str(BASE["LOADER"]),
        str(CRYPTO),
        "-o",
        str(out / "projection"),
    ]
    with (out / "build.log").open("xb") as log:
        subprocess.run(args, check=True, timeout=30, stdout=log, stderr=subprocess.STDOUT)
    return dict(
        status="PASS_RADV_PROJECTION_BUILD_ONLY",
        modules=modules,
        rhs=rhs,
        headers=HEADERS,
        header_commit=HEADER_COMMIT,
        cxx_sha256=sha(BASE["CXX"]),
        crypto_sha256=sha(CRYPTO),
        files={p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()},
        gpu_dispatches=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("backend", "headers", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        pinned = pin()
        row = build(a.backend, a.headers, a.new_output_dir)
        row["inputs"] = pinned
    except Exception as e:
        row = dict(status="FAIL_PRESERVED", reason=str(e))
    save(a.new_output_dir / "receipt.json", row)
    print(row["status"], row.get("reason", ""))
    raise SystemExit(int(row["status"] == "FAIL_PRESERVED"))
