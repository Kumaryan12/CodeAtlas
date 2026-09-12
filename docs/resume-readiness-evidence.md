# Resume-readiness follow-up

This follows the [project audit](project-audit.md). It preserves the earlier failures and adds a diagnosed fix, repeated live repair runs, and a clearer portfolio presentation.

## Diagnosed final-response failure

The original repair demo produced the correct patch and passing tests but ended with `invalid_agent_decision`. A new [diagnostic run](evaluation-repair-readiness/diagnostic-failure.json) reproduced it and exposed the safe validation categories:

```text
answer.claims.item.citation_ids: too_short
answer.claims.item.citation_ids: too_short
```

The model had placed statements without source citations into the answer's claims array. Draft changes and test outcomes have different evidence from original-source facts. The revised instructions explicitly put the draft/test report in the finish summary and reserve cited claims for original-source facts. The existing claim validator still requires nonempty citations, and the runtime still validates IDs against inspected snapshot evidence. No invalid decision is coerced into an accepted answer and no automatic retries were added.

Schema diagnostics now expose allowlisted field categories and validation types, never response values, extra-field names, prompts, secrets or hidden reasoning. A regression test confirms both the useful error categories and redaction of unexpected names/values. Another test confirms that empty citations remain rejected under the revised execution instructions.

## Repeated live repair results

One small, authored Python normalization bug; same functional checks as the earlier demo. These are **three follow-up attempts**, not an independently held-out benchmark. The diagnostic failure and original failed demo remain available.

| Attempt | Overall mechanical checks | Duration | Model calls | Original tests on final patch | Source preservation |
|---|---|---:|---:|---|---|
| [Run 1](evaluation-repair-readiness/run-1.json) | Pass | 35.1 s | 8 | 2/2 pass | Original unchanged; only auth.py drafted |
| [Run 2](evaluation-repair-readiness/run-2.json) | Pass | 36.0 s | 8 | 2/2 pass | Original unchanged; only auth.py drafted |
| [Run 3](evaluation-repair-readiness/run-3.json) | Pass | 41.0 s | 7 | 2/2 pass | Original unchanged; only auth.py drafted |

Every attempt begins with the original failing test, runs the actual Claude decision loop, reviews a diff, and invokes the approved Python Docker test profile. The harness independently reruns the original tests against the resulting patch and checks that the agent tested the final draft digest. No source repository is modified upstream.

**3/3 passing workflow checks does not mean 100% reliable agents or perfect citation faithfulness.** There are only three attempts on one deliberately small fixture. Model sampling and provider conditions can change the result. Median duration is 36.0 seconds; three observations do not justify a meaningful production p95 or throughput claim.

## Qualitative citation review

This is Codex-assisted review, not independent human annotation or an automatic accuracy score:

- **Run 1:** two claims correctly describe the original implementation and tests. A third claim describes the new draft while citing the original source. The patch is correct, but that claim's citation does not prove the change.
- **Run 2:** the final claims describe the original implementation and test expectations with their respective source citations. This is the clearest recorded example to demonstrate; the diff/test results separately establish the repair outcome.
- **Run 3:** the claim about the original implementation cites only `test_auth.py`. The tests establish expectations but do not establish the original function body. The test-expectation claim is supported.

Thus two runs retain citation-support flags despite accepted schemas and correct tested patches. These were not hidden or used to retroactively alter the mechanical grader. Claim-level support remains a separate improvement area.

## Verification

Core fix: `b05a6c4`. [Hosted CI](https://github.com/Kumaryan12/CodeAtlas/actions/runs/34714931552) passed after the change. The final local suite passed **242 backend tests with zero skips**, including real Docker and local embeddings. The scripted MCP agent evaluation also passed all six cases. The machine-readable [readiness metrics](evaluation-repair-readiness/summary.json) record the final local test results, model usage, durations and verification scope.

The frontend was not changed in this follow-up; its 23 passing tests and production build were verified in the preceding audit and checked again by hosted CI. Browser visual verification remains outstanding. Previously measured RAG accuracy/reliability limits were not retested or claimed fixed here.

## What is now ready

- A [copy-ready resume project entry](resume-ready.md), with defensible metrics and no production/banking claims.
- A [five-minute demo](demo.md), with honest recorded-run fallback and explicit setup.
- A revised README that leads with the project and evidence rather than milestone history.
- Reproducible live repair evidence, safe failure diagnostics, strict validation and a documented unresolved citation-quality problem.

Use Run 2 as a clearly labelled recorded demonstration, and show the other results when discussing evaluation. The goal is to explain both what the system does and what the evidence does not establish.
