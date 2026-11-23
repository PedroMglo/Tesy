# ADR: publish the independent scale lab on Tesy's existing Git remote

Status: accepted by the owner's later instruction to publish the completed work in Git and their explicit selection of the existing Tesy repository. Decision date: 2026-09-26. This ADR records publication provenance and rollback; it does not change the model/runtime design.

## Reason and scope

The requested sibling lab path was outside the authorized writable roots, so the work was created as a separate nested Git repository under `/home/pmglo/Projects/Tesy/tesy-scale-lab`. Its branch `scale-lab` has an independent history. The owner chose the existing public `https://github.com/PedroMglo/Tesy.git` repository as its remote destination. Publish **only** this lab branch to `refs/heads/scale-lab`. Do not merge it into `main`, alter the root Tesy PR stack, push to another project, create a PR/issue, publish a package/image, or force-push. The remote branch is a standalone lab tree, not a proposed replacement of Tesy's main tree.

## Provenance and licence

The lab's scripts, manifests, synthetic prompts and research notes were created for this campaign. Backend source checkouts and build products are excluded from Git. The backend identities are pinned to stock `ggml-org/llama.cpp` SHA `4b1a27fa0eb875bbca4f6cfe936e3d65adc685c0` and `freedomljc/llama.cpp` SHA `1248fd8fa8cfebaece5ea992e4d951c1e18bb9d5`; both local checkouts carry the ggml authors' MIT licence. The small diagnostic patch under `patches/` applies to an isolated MIT-licensed backend worktree and is not a fork publication. Model weights are excluded; only artefact identifiers, revisions, sizes and verified SHA-256 hashes are committed. No copyright or redistribution licence for model weights is inferred. The lab branch does not add a new general licence grant for its original material; that is a separate owner decision.

The publication contains compact structured evidence and source scripts. Raw stdout/stderr, one-second samples, float32 logit dumps, caches, model weights and compiler outputs remain local and ignored according to the frozen run publication policies and repository boundaries. The compact records include hashes and limitations so omitted raw data is not passed off as fully public reproducibility.

## Reversal and verification

The reversible publication unit is the remote `scale-lab` branch. If the owner later requests withdrawal, a deliberate deletion of that branch can remove the branch pointer without touching `main`; history may persist in remote caches, so deletion is not a confidentiality remedy. No deletion is authorized now. Verify publication by comparing local `HEAD` to `git ls-remote origin refs/heads/scale-lab` and verify `main` remains at its pre-publication SHA `7a7d3dcbd1ff8e594ac57459c3db06306083c3ca`. Keep the local nested lab Git history as the record regardless of remote state.
