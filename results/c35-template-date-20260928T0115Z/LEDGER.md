# C35 template date boundary

- Prospective two-arm synthetic session diagnostic. C29 and C34b FAILs remain unchanged. Backend patch is opt-in, same embedded GGUF template; model-free Jinja test and 15 focused Python tests pass. No physical C35 run yet.
- Control launch rejected by `check_scope()` before idle/model because the command lacked `systemd-run --user --scope`; no cache output. C35 closed FAIL_HARNESS_PRELAUNCH_SCOPE_NO_MODEL. C35b requires a new identity.
