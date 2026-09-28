# C41 8K boundary

- Frozen before output: P12, 7936 official prompt IDs, cap 256, synthetic first-line retrieval, E18 and CPU100 thermal policy. Source is the C35 date-fixed server; C40 quality result is the parent checkpoint.
- One fresh process; no retry. Raw stays local outside Git. C15 remains NOT_RUN.
- Prelaunch `--measurement-commit 9cc8b3b` failed `C41 measurement worktree not frozen`: the wrapper compares the full SHA. No idle admission, model load, API request, raw run or output occurred. GPU and port 18367 were clear afterward. This identity remains failed; the corrected invocation belongs to C41b.
