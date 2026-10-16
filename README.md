# harness-core

The generic part of a Claude Code harness, shared by a personal harness and a work harness. Nothing here may name an employer, a work system, a work identity or a secret.

## Layout

| Path | Purpose |
| --- | --- |
| `core/` | The shared content: generic rules, hooks, skills, scripts. Each harness vendors this folder as `core/`. |
| `scan/scan_core.py` | The scan gate. Every promotion into `core/` runs it. Exit 0 clean, 1 findings, 2 something unread. |
| `scan/test_scan_core.py` | Tests for the gate, one case per blocked class. |

## Rules

1. A file reaches `core/` only by promotion from a harness, through the reconcile tool, after `scan_core.py` exits 0.
2. A file that fits only one side stays in that harness and is tagged `personal` or `work` in that harness's `harness.manifest.yaml`.
3. Edits to `core/` made inside a harness are promoted back, never left as a silent fork.

Run the tests: `python -I scan/test_scan_core.py`
