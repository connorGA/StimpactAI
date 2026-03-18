# Harness Self-Test

The harness self-test exercises one complete end-to-end scenario on a small fixture repository.

It validates:

- initializer session setup
- `init.sh` generation
- `.stimpactai/features.json` generation
- guarded file editing with syntax validation
- browser verification through the orchestrator
- feature verification state updates
- git checkpoint creation and diff inspection
- prompt context accumulation

## Run Locally

From the repository root:

```bash
.venv/bin/python -m pytest agent-platform/tests/test_harness_self_test.py -q
```

Or from `agent-platform/`:

```bash
../.venv/bin/python -m pytest tests/test_harness_self_test.py -q
```
