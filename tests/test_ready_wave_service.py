import gzip
import hashlib
import json
from collections import Counter
from itertools import pairwise
from pathlib import Path
from runpy import run_path

import pytest

HERE = Path(__file__).resolve().parents[1] / "research/ready-experts/layer/prefix/wave"
study = run_path(HERE / "review.py")


def test_public_measurement_and_composition():
    assert study["review"]() == {
        "physical_merge": "INCONCLUSIVE",
        "physical_promotion": "GO_LOCAL",
        "composed": {"P97": "NO_GO_FIXED_COST", "P106": "NO_GO_FIXED_COST"},
    }


@pytest.mark.parametrize("damage", ["generation", "read", "buffer", "consumer"])
def test_consumer_applies_seven_real_publications(damage):
    e = HERE / "evidence-20261128-r01"
    rows = (
        json.loads(line)
        for line in gzip.decompress((e / "arms.jsonl.gz").read_bytes()).splitlines()
    )
    row = next(r for r in rows if r["mode"] == "M")
    pins = json.loads((e / "physical.json").read_bytes())["selection"]
    if damage == "generation":
        row["published"]["47"]["gen"] -= 1
    elif damage == "read":
        row["reads"].append(row["reads"][0])
    elif damage == "buffer":
        row["reads"][0]["worker"] = (row["reads"][0]["worker"] + 1) % 4
    else:
        row["resumed"] = min(p["at"] for p in row["published"].values())
    with pytest.raises(ValueError):
        study["G"]["validate"](row, pins)


def test_training_joins_all_components_without_cycles():
    batches = [[1, 3]] * 5 + [[2, 4]] * 3 + [[3, 4]] * 2 + [[1, 4]]
    path, score = study["L"]["linear_order"](batches, 6)
    assert sorted(path) == list(range(6))
    assert score == sum(a in b and c in b for a, c in pairwise(path) for b in batches)
    assert score == 10
    assert study["L"]["linear_order"](reversed(batches), 6) == (path, score)


def test_two_live_tile_places_and_shared_edge_credit():
    p = study["P"]
    # The fast first stage stalls until the tail releases a place for tile 3.
    assert p["pipeline"]([(1, 20), (2, 3), (4, 5)]) == [
        [0, 1, 1, 21],
        [1, 3, 21, 24],
        [21, 25, 25, 30],
    ]
    assert p["kept"](2, 10, [(1, 5), (4, 9), (12, 15)]) == 1
    assert p["budget"](16, 2)["minimum_payload_Bps"] == 8_000_000_000
    assert p["budget"](16, 0)["minimum_payload_Bps"] is None


def test_ram_source_breaks_a_disk_run():
    jobs = [[e, 5, 1] for e in (0, 1, 2, 3, 4)]
    hits, paired, after, before = study["K"]["sources"](jobs, list(range(6)), {1, 2})
    assert hits == {1, 2} and paired == {3, 4} and (after, before) == (1, 4)
    with pytest.raises(ValueError, match="duplicate"):
        study["K"]["sources"]([*jobs, jobs[0]], list(range(6)), {1, 2})


def test_renewable_pool_promotes_before_recycling_a_slot():
    tier = run_path(HERE / "tier_bank.py")
    a, b, c = (0, 0), (0, 1), (0, 2)
    pool = tier["Pool"](1, [a], Counter({a: 4, b: 3, c: 1}))
    assert pool.reserve(a, b) == (0, 0)
    assert pool.reserve(a, c) == (None, None)
    assert pool.held == {b: 0}
    assert pool.reserve(b, c) == (0, 0)
    assert pool.held == {c: 0} and pool.peak == 1


def test_partition_replays_all_owners_and_prices():
    tier = run_path(HERE / "tier_bank.py")
    root = HERE / "evidence-tier-20261128-r01"
    receipt = json.loads((root / "receipt.json").read_bytes())
    raw = (root / "transactions.json.gz").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == receipt["transactions_sha256"]
    assert tier["SRC"]["digest"](HERE / "tier_bank.py") == receipt["source_sha256"]
    assert tier["SRC"]["digest"](HERE / "tier-bank.md") == receipt["protocol_sha256"]
    w = json.loads(gzip.decompress(raw))
    result = tier["assess"](w)
    assert result == receipt["result"]
    assert result["caps"] == [252, 101] and result["different_global_hit_decisions"] == 17
    assert result["partition"]["hits"] == dict(prefill=371, early_decode=299, tail=4)
    w["reservations"][0][4] += 1
    with pytest.raises(ValueError, match="primary generation"):
        tier["assess"](w)
