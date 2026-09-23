# Model download helper

Tesy never downloads large model weights implicitly.

Dry-run command:

```bash
tesy models download gpt-oss-20b-mxfp4-gguf \
  --destination ~/.local/share/tesy/models/gpt-oss-20b
```

This only prints a lock-derived plan.

Explicit execution requires both flags:

```bash
tesy models download gpt-oss-20b-mxfp4-gguf \
  --destination ~/.local/share/tesy/models/gpt-oss-20b \
  --execute --yes
```

The model entry must contain an exact repository, revision and filename.
A symlink destination is rejected.

Successful download is not identity validation. Run `tesy models verify`
afterwards; filename, exact byte count and SHA-256 remain authoritative.
