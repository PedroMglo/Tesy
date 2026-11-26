"""Check both serial and speculative paths at the server's common sampled-token site."""

import re
from itertools import pairwise
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
PLAN = run_path(str(HERE.parent / "run.py"))
V = run_path(str(PLAN["QUAL"] / "history_lookup/native_ids/verify.py"))
need = PLAN["need"]
DRAFT = re.compile(
    V["CLOCK"] + rb"D slot handle_last_: id  0 \| task ([0-9]+) \| generate_draft: "
    rb"id=([0-9]+), #tokens=([0-9]+), #draft=([0-9]+), pos_next=([0-9]+)\n"
)
# SLT_DBG uses __func__ inside a C++ lambda for the verification loop.
ACCEPT = re.compile(
    V["CLOCK"] + rb"D slot [^\n|:]*: id  0 \| task ([0-9]+) \| "
    rb"add accepted tokens: sampled=([0-9]+), ids.size=([0-9]+), n_draft=([0-9]+)\n"
)


def grade(log, index, data, plan, mode):
    label = f"T{index}"
    prompt, target = data[label]["prompt"], data[label]["target"]
    events = list(V["events"](log))
    tasks = [task for _, task, event in events if event[0] == "start"]
    need(len(tasks) == len(set(tasks)) and index <= len(tasks) <= 2, "task starts")
    task = tasks[index - 1]
    track = [(clock, event) for clock, owner, event in events if owner == task]
    need(all(a[0] <= b[0] for a, b in pairwise(track)), "native clock reversal")
    observed = [event for _, event in track]
    need(
        observed[0] == ("start",)
        and observed[-1] == ("end", len(prompt) + len(target) - 1)
        and [e[0] for e in observed if e[0] != "feed"]
        == ["start", *(["sample"] * (len(target) - 1)), "eos", "sample", "end"],
        "sample, EOG or release lifecycle",
    )
    samples = [e for e in observed if e[0] == "sample"]
    for i, (sample, token) in enumerate(zip(samples, target, strict=True), start=1):
        need(sample[1:3] == (i, 256 - i), f"{label} budget at {i}")
        need(sample[3] == token, f"{label} greedy ID mismatch at position {i - 1}")
    if mode == "ON":
        steps = plan[label]
    else:
        steps = [dict(at=j, proposal=[], accepted=0) for j in range(1, len(target))]
    batches = []
    accepted = []
    feeds = []
    for step in steps:
        at, width = step["at"], len(step["proposal"])
        pos = len(prompt) + at - 1
        if width:
            batches.append((target[at - 1], pos, width, pos))
            k = step["accepted"]
            need(at + k < len(target), "unknown bonus")
            accepted.append((target[at + k], k + 1, width))
        else:
            feeds.append(("feed", target[at - 1], pos))
    need([e for e in observed if e[0] == "feed"] == feeds, "serial input IDs or positions")

    def rows(regex):
        return [
            tuple(map(int, m.groups()[5:])) for m in regex.finditer(log) if int(m.group(5)) == task
        ]

    need(rows(DRAFT) == batches, "native draft batches or positions")
    need(rows(ACCEPT) == accepted, "native accepted depths or bonus")
    return dict(
        task=task,
        sampled=len(samples),
        sampled_sha256=V["digest"](V["ids_bytes"]([s[3] for s in samples])),
        serial=len(feeds),
        blocks=len(batches),
        proposed=sum(row[2] for row in batches),
        accepted=sum(row[1] - 1 for row in accepted),
        eos=1,
    )
