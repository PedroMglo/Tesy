# GitHub Stack #22 handoff

Date: 2026-09-24

Objective: make the existing PR chain an official GitHub Stacked PRs object
rooted at `main`, without rewriting branches.

Audit base: Tesy `ca4100e755cea2e0261e4a550af1c9681b64b4e4`, tree
`83917e86dc20fa5e5e8115901de9c5206ca5aef1`; `origin/main`
`a8a0d21bb5b4844f7226e5ae7f5cec17eadcb44f`.

## Evidence and decision

GitHub reported that #18 had merged into `main`, while #9 still targeted the
superseded sweep branch. The first `gh stack link --base main --remote origin`
attempt found the already-existing Stack #20 and failed to update #9's base
with HTTP 422 (`PullRequest.base is invalid`). Stack #20's trunk remained the
superseded branch. Because Stack #20 contained only the 11 open PRs, it was
unstacked with `gh stack unstack 20`; the same bottom-to-top `gh stack link`
then created Stack #22 and updated #9's base to `main`.

Confirmed Stack #22 order, bottom to top:
`#9 → #11 → #10 → #12 → #13 → #14 → #15 → #16 → #17 → #19 → #21`.
`gh stack view --short` shows `main` as trunk. The #21 remains a draft above
#19. No branch was rebased, force-pushed, or merged during this repair.

## Remaining bottom-layer conflict

The remote #9 head was `50944909a7eb5af3b4a95e7398e67072fb08c029`.
GitHub showed `baseRefName=main` and `mergeable=CONFLICTING`. A read-only
comparison of `origin/main` with the remote #9 branch found 50 main-only and
70 #9-only commits. `git merge-tree` showed real overlaps including
`IMPLEMENTATION_STATUS.md`, sweep and bring-up research records, and bootstrap
and diagnostic scripts. The local #9 branch was two commits behind its remote
head at the time of audit, so the remote head is the authority for this delta.

## Alternatives, tests, limitations, next gate

Retargeting a stacked PR directly was rejected by GitHub. Removing and
recreating the stack grouping preserved the open PRs and their branch tips;
the merged #18 was outside that grouping. Stack membership and #9's base were
verified with `gh stack view` and `gh pr view`. Merge-conflict resolution and
integration tests are **NOT_RUN**. The next stack gate is deliberate resolution
of #9 against `main`, followed by bottom-up validation and merges. Preserve
GitHub Stacked PRs, do not force-push, and do not use `gh stack rebase` or
`gh stack push` under the current repository rule.
