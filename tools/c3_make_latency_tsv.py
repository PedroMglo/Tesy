#!/usr/bin/env python3
"""Derive a simple no-replace token-ID TSV for the native P1 probe."""

import hashlib
import json
from pathlib import Path

source=Path("results/c3-p1-latency-ids01.json")
target=Path("results/c3-p1-latency-ids01.tsv")
manifest=Path("results/c3-p1-latency-ids01-derivation.json")
data=json.loads(source.read_text())
if data["schema"]!="c3-p1-latency-ids-v1" or \
   [(row["id"],row["token_count"]) for row in data["rows"]]!=[
       ("latency-short",113),("latency-medium",496),("latency-long",1522)]:
    raise ValueError("frozen IDs changed")
text="".join(row["id"]+"\t"+",".join(map(str,row["ids"]))+"\n" for row in data["rows"])
with target.open("x") as out:out.write(text)
report={"schema":"c3-p1-ids-derivation-v1",
        "source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
        "tsv_sha256":hashlib.sha256(target.read_bytes()).hexdigest(),
        "tool_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "counts":[113,496,1522]}
with manifest.open("x") as out:json.dump(report,out,indent=2);out.write("\n")
print(json.dumps(report))
