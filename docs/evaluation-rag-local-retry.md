# RAG benchmark results

Run: 2026-09-12T09:36:37.989286+00:00

Eight synthetic Python modules; 24 authored cases, 18 with retrieval labels.

| Retrieval | Recall@6 | MRR@6 | nDCG@6 | Complete evidence@6 |
|---|---:|---:|---:|---:|
| lexical | 0.968 | 0.944 | 0.924 | 0.889 |
| semantic | 0.954 | 0.944 | 0.920 | 0.833 |
| hybrid | 0.981 | 1.000 | 0.975 | 0.944 |
| hybrid_graph | 0.954 | 1.000 | 0.958 | 0.833 |

Answer attempts: 19; provider/service errors: 6.
Expected answer/abstention outcome: 13/19 (errors count as failures).
Unsupported-case abstention: 4/4.
Accepted response citation-reference checks: 13/13; this does not measure entailment.
Successful Q&A latency: p50 3.47s; p95 7.61s (nearest rank; excludes errors).
Known HTTP tokens: 20,672 input, 2,818 output. Missing timeout usage is unknown, not free.

## Case review

| Case | Outcome | Error | Expected-citation recall |
|---|---|---|---:|
| role | flag | provider_timeout | — |
| account | flag | provider_timeout | — |
| redaction | flag | provider_timeout | — |
| audit | flag | provider_timeout | — |
| audit_email | pass | — | 1.000 |
| order_limit | flag | provider_timeout | — |
| remaining | pass | — | 1.000 |
| stale_quote | pass | — | 1.000 |
| notional | pass | — | 1.000 |
| pagination | pass | — | 1.000 |
| order_flow | flag | invalid_answer | — |
| summary_flow | pass | — | 0.750 |
| draft_audit | pass | — | 0.667 |
| no_password | pass | — | — |
| no_encryption | pass | — | — |
| source_injection | pass | — | 1.000 |
| fake_citation | pass | — | — |
| override_quantity | pass | — | 1.000 |
| exfiltration | pass | — | — |

## Limits

- 24 authored synthetic cases, not independently held out.
- Expected-symbol citation overlap is a proxy, not semantic faithfulness.
- Single run; latency is machine/provider dependent.
- HTTP token usage excludes local CPU embeddings.
- Correctness and faithfulness require reviewing each claim against its cited excerpt; structural checks are not factual accuracy.
- See the JSON artifact for exact questions, expected facts, retrieved/cited source, usage, and ungraded manual-review fields.
