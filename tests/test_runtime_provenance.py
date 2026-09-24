from pathlib import Path

from tesy.runtime_provenance import (
    RuntimeProvenanceError,
    parse_proc_cmdline,
    parse_proc_maps,
    validate_runtime_identity,
)


def _build_provenance(server: Path, cuda: Path) -> dict:
    return {
        "schema": "tesy.llama_build_provenance.v1",
        "status": "PASS",
        "binaries": {
            "llama_server": {
                "path": str(server.resolve()),
            },
            "ggml_cuda": {
                "path": str(cuda.resolve()),
                "inode": cuda.stat().st_ino,
            },
        },
    }


def test_parse_proc_maps_selects_and_deduplicates_backend_libraries():
    text = """\
1000-2000 r--p 00000000 08:01 101 /tmp/libggml-cuda.so
2000-3000 r-xp 00001000 08:01 101 /tmp/libggml-cuda.so
3000-4000 r--p 00000000 08:01 102 /usr/lib/libcuda.so.1
4000-5000 r--p 00000000 08:01 103 /usr/lib/libsomething.so
5000-6000 r--p 00000000 08:01 104 [heap]
"""
    assert parse_proc_maps(text) == [
        {
            "path": "/tmp/libggml-cuda.so",
            "inode": 101,
            "device": "08:01",
            "deleted": False,
        },
        {
            "path": "/usr/lib/libcuda.so.1",
            "inode": 102,
            "device": "08:01",
            "deleted": False,
        },
    ]


def test_parse_proc_maps_preserves_deleted_marker():
    rows = parse_proc_maps(
        "1000-2000 r-xp 00000000 08:01 101 "
        "/tmp/libggml-cuda.so (deleted)\n"
    )
    assert rows == [
        {
            "path": "/tmp/libggml-cuda.so",
            "inode": 101,
            "device": "08:01",
            "deleted": True,
        }
    ]


def test_validate_runtime_identity_accepts_exact_server_and_cuda_mapping(tmp_path):
    server = tmp_path / "llama-server"
    cuda = tmp_path / "libggml-cuda.so"
    server.write_text("server", encoding="utf-8")
    cuda.write_text("cuda", encoding="utf-8")

    mismatches = validate_runtime_identity(
        executable=server,
        libraries=[
            {
                "path": str(cuda),
                "inode": cuda.stat().st_ino,
                "device": "08:01",
                "deleted": False,
            }
        ],
        build_provenance=_build_provenance(server, cuda),
    )

    assert mismatches == []


def test_validate_runtime_identity_rejects_wrong_executable_and_missing_cuda(tmp_path):
    server = tmp_path / "llama-server"
    wrong = tmp_path / "other-server"
    cuda = tmp_path / "libggml-cuda.so"
    server.write_text("server", encoding="utf-8")
    wrong.write_text("wrong", encoding="utf-8")
    cuda.write_text("cuda", encoding="utf-8")

    mismatches = validate_runtime_identity(
        executable=wrong,
        libraries=[],
        build_provenance=_build_provenance(server, cuda),
    )

    assert any(item.startswith("process executable:") for item in mismatches)
    assert "expected exactly one mapped ggml-cuda identity, got 0" in mismatches


def test_validate_runtime_identity_rejects_deleted_cuda_mapping(tmp_path):
    server = tmp_path / "llama-server"
    cuda = tmp_path / "libggml-cuda.so"
    server.write_text("server", encoding="utf-8")
    cuda.write_text("cuda", encoding="utf-8")

    mismatches = validate_runtime_identity(
        executable=server,
        libraries=[
            {
                "path": str(cuda),
                "inode": cuda.stat().st_ino,
                "device": "08:01",
                "deleted": True,
            }
        ],
        build_provenance=_build_provenance(server, cuda),
    )

    assert any(item.startswith("selected mapped libraries are deleted:") for item in mismatches)
    assert "expected exactly one mapped ggml-cuda identity, got 0" in mismatches



def test_parse_proc_cmdline_accepts_exact_utf8_argv():
    data = b"/tmp/llama-server\0--model\0/tmp/model.gguf\0--fit\0off\0"
    assert parse_proc_cmdline(data) == [
        "/tmp/llama-server",
        "--model",
        "/tmp/model.gguf",
        "--fit",
        "off",
    ]


def test_parse_proc_cmdline_rejects_empty_argument():
    import pytest

    with pytest.raises(RuntimeProvenanceError, match="empty argv element"):
        parse_proc_cmdline(b"/tmp/llama-server\0\0--fit\0off\0")


def test_validate_runtime_identity_accepts_exact_argv(tmp_path):
    server = tmp_path / "llama-server"
    cuda = tmp_path / "libggml-cuda.so"
    server.write_text("server", encoding="utf-8")
    cuda.write_text("cuda", encoding="utf-8")
    argv = [str(server), "--model", "/tmp/model.gguf", "--fit", "off"]

    mismatches = validate_runtime_identity(
        executable=server,
        libraries=[
            {
                "path": str(cuda),
                "inode": cuda.stat().st_ino,
                "device": "08:01",
                "deleted": False,
            }
        ],
        build_provenance=_build_provenance(server, cuda),
        observed_argv=argv,
        expected_argv=argv,
    )

    assert mismatches == []


def test_validate_runtime_identity_rejects_argv_mismatch(tmp_path):
    server = tmp_path / "llama-server"
    cuda = tmp_path / "libggml-cuda.so"
    server.write_text("server", encoding="utf-8")
    cuda.write_text("cuda", encoding="utf-8")

    mismatches = validate_runtime_identity(
        executable=server,
        libraries=[
            {
                "path": str(cuda),
                "inode": cuda.stat().st_ino,
                "device": "08:01",
                "deleted": False,
            }
        ],
        build_provenance=_build_provenance(server, cuda),
        observed_argv=[str(server), "--fit", "on"],
        expected_argv=[str(server), "--fit", "off"],
    )

    assert "process argv does not exactly match frozen expected argv" in mismatches
