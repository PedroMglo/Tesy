import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "broken_pfj", Path(__file__).with_name("incomplete.py")
)
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


def test_torn_unsealed_capture_with_one_identifiable_slot(tmp_path):
    pfj = diagnostic.pfj
    path = tmp_path / "torn.pfj"
    header = pfj.HEADER.pack(b"TESYPF1\0", 1, 96, 262144, 0, 0, 0, 0)
    fields = [0] * len(pfj.Row._fields)
    fields[0] = 123
    fields[6] = 1
    path.write_bytes(header + pfj.RECORD.pack(*fields) + bytes(13))
    evidence = diagnostic.inspect(path)
    assert evidence["qualification"] == "INCONCLUSIVE_INCOMPLETE_JOURNAL"
    assert evidence["sealed"] is False and evidence["observed_event_slots"] == {"ENTER": 1}
    assert evidence["trailing_partial_bytes"] == 13
