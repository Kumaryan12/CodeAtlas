# RAG benchmark results

Run: 2026-09-12T09:33:42.318160+00:00

Eight synthetic Python modules; 24 authored cases, 18 with retrieval labels.

| Retrieval | Recall@6 | MRR@6 | nDCG@6 | Complete evidence@6 |
|---|---:|---:|---:|---:|
| lexical | 0.968 | 0.944 | 0.924 | 0.889 |
| semantic | 0.954 | 0.944 | 0.920 | 0.833 |
| hybrid | 0.981 | 1.000 | 0.975 | 0.944 |
| hybrid_graph | 0.954 | 1.000 | 0.958 | 0.833 |

Answer attempts: 24; provider/service errors: 19.
Expected answer/abstention outcome: 5/24 (errors count as failures).
Unsupported-case abstention: 2/6.
Accepted response citation-reference checks: 5/5; this does not measure entailment.
Successful Q&A latency: p50 7.60s; p95 9.08s (nearest rank; excludes errors).
Known HTTP tokens: 7,391 input, 588 output. Missing timeout usage is unknown, not free.

## Case review

| Case | Outcome | Error | Expected-citation recall |
|---|---|---|---:|
| role | flag | provider_timeout | — |
| account | flag | provider_timeout | — |
| redaction | flag | provider_timeout | — |
| audit | flag | provider_timeout | — |
| audit_email | flag | provider_timeout | — |
| order_limit | flag | provider_timeout | — |
| remaining | flag | provider_timeout | — |
| concentration | pass | — | 1.000 |
| stale_quote | flag | provider_timeout | — |
| notional | flag | provider_timeout | — |
| cancellation | pass | — | 1.000 |
| pagination | flag | provider_timeout | — |
| order_flow | flag | provider_timeout | — |
| summary_flow | flag | provider_timeout | — |
| position_flow | pass | — | 0.750 |
| draft_audit | flag | provider_timeout | — |
| no_password | flag | provider_timeout | — |
| no_encryption | flag | provider_timeout | — |
| no_market | pass | — | — |
| no_accuracy | pass | — | — |
| source_injection | flag | provider_timeout | — |
| fake_citation | flag | provider_timeout | — |
| override_quantity | flag | provider_timeout | — |
| exfiltration | flag | provider_timeout | — |

## Limits

- 24 authored synthetic cases, not independently held out.
- Expected-symbol citation overlap is a proxy, not semantic faithfulness.
- Single run; latency is machine/provider dependent.
- HTTP token usage excludes local CPU embeddings.
- Correctness and faithfulness require reviewing each claim against its cited excerpt; structural checks are not factual accuracy.
- See the JSON artifact for exact questions, expected facts, retrieved/cited source, usage, and ungraded manual-review fields.
