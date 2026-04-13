# Benchmarks And Canary

## Benchmark Corpus

The repository already contains a broad drill corpus in `agent-platform/staging_drill.py`.

Current scenario families include:

- direct single-file bugs
- imported helper indirection
- misleading stacktraces
- wide search-space failures
- multi-file cascading failures
- env-config failures
- wrong-first-fix pressure
- frontend verification drills

These scenarios are evaluation data for the harness. They are not deterministic repair templates.

## Useful Commands

Write the current manifest:

```bash
python agent-platform/staging_drill.py --write-manifest /tmp/stimpact-benchmark-manifest.json
```

Summarize prior benchmark results:

```bash
python agent-platform/staging_drill.py --summarize-results-dir .stimpactai/autonomous-runs
```

Run the drill test suite:

```bash
python -m pytest agent-platform/tests/test_staging_drill.py -q
```

## Staging Canary Sequence

1. Pick a dedicated non-production repo or branch that is already connected through onboarding.
2. Confirm onboarding step 6 shows:
   - recent heartbeat or a consciously accepted warning
   - a resolved service mapping
   - a repo profile with reproduce and verify commands
   - no blocked harness readiness checks
3. Seed one drill scenario or one intentional bug into that repo.
4. Redeploy the staging service.
5. Confirm the SDK creates a fresh incident.
6. Launch the autonomous run.
7. Review:
   - reproduction success
   - verification evidence
   - retry behavior
   - whether the run stopped safely when evidence was weak
8. Record the result with the scenario id or bug class so it can be included in benchmark summaries later.

## Success Criteria

- The agent finds the right area of the repo without hand-authored fix logic.
- The sandbox reproduces and verifies with the configured contract.
- The run either converges to a verified fix or fails in a legible, evidence-backed way.
