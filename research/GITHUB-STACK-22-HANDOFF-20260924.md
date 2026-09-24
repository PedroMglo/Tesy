# GitHub Stack #22 handoff

Date: 2026-09-24

Objective: keep the existing PR chain as an official GitHub Stacked PRs object
rooted at `main`, repair the stale ancestry without rewriting branches, and
preserve each PR's immediate delta.

Audit base: `origin/main@a8a0d21bb5b4844f7226e5ae7f5cec17eadcb44f`.

## Stack order

Confirmed bottom to top:
`#9 → #11 → #10 → #12 → #13 → #14 → #15 → #16 → #17 → #19 → #21`.

Only the lowest unmerged PR is a merge candidate. Upper PRs remain stacked on
their immediate predecessor until the lower layer merges.

## Repair result

PR #18 had already merged the restacked Pareto-sweep hardening into `main`.
The historical #9 branch had diverged from that base and GitHub reported a real
merge conflict.

The repair did not rebase or force-push any branch. #9 was advanced by a
fast-forward merge commit, `78bf912aadcdba934e65f86a68ed53d714feecae`,
with the former #9 head and current `main` as parents. Its tree is based on
current `main` and reapplies only the 39-file capacity-gate delta. The shared
B0/B1/Pareto files preserve the hardening already merged through #18.

The repaired ancestry was then propagated bottom-up through every dependent
branch using fast-forward merge commits, preserving each PR's immediate delta.

## Final structural audit

GitHub comparison after propagation reports every open PR in Stack #22 as
`ahead` of its immediate base with `behind=0`, and every PR reports
`mergeable=true`.

Current heads:
- #9: `78bf912aadcdba934e65f86a68ed53d714feecae`
- #11: `9a5e0038bce47570ceb64c7c7daca8675cf37b92`
- #10: `21bfa492fd0d0c93cd45bcffda24d19f85fdc533`
- #12: `fd538d1dc30ce6aae1e8edf72e0235aedd17b325`
- #13: `c32fc47a87e7fe6211fac94ae3b07fdac174aac3`
- #14: `e69704f0915518c17393d812229e6a2807132975`
- #15: `9979c40e53e7bed84a0c0c182e5524c4b841d982`
- #16: `67a6a882d56efa0671a6818b679ca769d4f6c272`
- #17: `718a0e361c38e11491cff0f1c39cc911fc6ffcb4`
- #19: `e5a32bf2251e8a87e9d278fd4166fadb7e621b0f`
- #21 before this handoff update: `b6ed3f1be48e6fa431e8832764afbd6ed169804b`.

Review-thread audit found zero unresolved inline review threads across the stack
before promotion. No merge or auto-merge was performed.

## Validation boundary and next gate

The restack itself is a Git-graph/content reconciliation. Repository tests were
**NOT_RUN_AFTER_RESTACK** locally because this repair was performed through the
GitHub object/API boundary, not a physical-host worktree.

The lowest layer, #9, is the next review/merge candidate. Marking it ready for
review triggers the repository CI review gate; CI status is authoritative for
the repaired head. PRs above #9 remain draft until the lower dependency is
accepted and merged, after which their bases/deltas must be rediscovered before
promotion.
