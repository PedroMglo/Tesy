# C41 prelaunch failure

- Objective: one P12 7936+256 8K synthetic retrieval under E18, after C40 quality closure. Base `9cc8b3b7f0efc1860234747081d6485c6d353e4d`; frozen protocol and model-free tokenizer bridge passed.
- Evidence: the launcher supplied `--measurement-commit 9cc8b3b` while the harness requires the full `git rev-parse HEAD`. It rejected the worktree identity before idle, model load or request. GPU and port 18367 were empty afterward. Evidence class: observed harness prelaunch failure; model result NOT_RUN.
- Decision: preserve this identity as `FAIL_HARNESS_COMMIT_ARGUMENT_NO_MODEL`. No threshold, workload, backend or guard changed. A new C41b identity may use the full SHA after fresh preflight.
- Alternatives/limits: this says nothing about the 8K model boundary. C15 full-model remains NOT_RUN. No default change.
