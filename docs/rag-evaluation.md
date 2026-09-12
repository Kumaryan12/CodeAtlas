# Local embeddings and RAG evaluation

CodeAtlas can run embeddings on the API server CPU while Claude generates cited answers. No OpenAI key is needed in local mode. Retrieved source is still sent to the configured answer provider when asking a question.

## Setup

From the repository root, install the optional model dependencies and download the pinned public weights once:

```sh
apps/api/.venv/bin/pip install -e 'apps/api[local]'
apps/api/.venv/bin/python -m codeatlas.ai.local_embeddings --prepare
```

Set `CODEATLAS_EMBEDDING_PROVIDER=local` in `.env`, retain the configured Anthropic key, restart the API, then build/rebuild each snapshot's semantic index. Normal embedding inference uses cached weights only and CPU; it does not download models or call a remote embedding API. Missing dependencies or weights produce a setup error. Set `CODEATLAS_EMBEDDING_PROVIDER=openai` to use the existing OpenAI adapter with its key instead.

The model is [all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2), pinned to revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, with 384-dimensional vectors. This is a generic English encoder, not a code-specialized model. Its normal 256-token limit would truncate long code chunks. Our adapter splits into 254 content-token windows, adds CLS/SEP, uses attention-masked mean pooling and normalization, then combines window vectors weighted by content-token count and normalizes again. This preserves the tail but can dilute specific details. The model revision, pooling version, and chunk version participate in the index fingerprint.

## Reproduce

```sh
# No models, network, or API keys; included in CI.
apps/api/.venv/bin/python -m codeatlas.evaluation.rag --offline --output /tmp/rag-offline.json
# Real CPU embeddings, four retrieval ablations, no answer API calls.
apps/api/.venv/bin/python -m codeatlas.evaluation.rag --output /tmp/rag-local.json
# Real embeddings plus 24 Claude answer calls; checkpoints after each answer.
apps/api/.venv/bin/python -m codeatlas.evaluation.rag --answers --output /tmp/rag-live.json
# Real local-model regression, after preparing weights.
CODEATLAS_TEST_LOCAL_EMBEDDINGS=1 apps/api/.venv/bin/pytest apps/api/tests/test_rag_benchmark.py -q
```

The runner creates an isolated SQLite database, parses fixture source without executing it, and uses production indexing and Q&A services. All retrieval modes use the same chunks, questions and embeddings. The benchmark records corpus and question hashes, configuration, ranked results, claims, cited excerpts, latency and available HTTP token usage. Local CPU compute has no provider token charge; hardware cost is not estimated.

## Dataset and metrics

`apps/api/evaluation/rag_cases.json` freezes 24 authored questions over eight small synthetic financial-services modules: exact symbols, paraphrases, cross-file flows, unsupported questions, and adversarial requests/comments. Eighteen have positive relevance labels; six require abstention. It is separate from the original 12 development questions, but is **not independently held out**, representative of real banking workloads, or proof of production safety.

Ranking metrics macro-average over positive cases only, at k=1,3,6:

- Precision: relevant returned symbols / k; missing slots count against precision.
- Recall: relevant returned symbols / all labelled relevant symbols.
- MRR: reciprocal rank of the first relevant symbol.
- nDCG: binary relevance with logarithmic rank discount, normalized by the ideal ranking.
- Complete evidence: fraction retrieving every labelled symbol.

Duplicate symbols receive credit once. Unanswerable cases are excluded from ranking metrics and evaluated for answer abstention. Outcomes distinguish provider errors from legitimate abstentions. Valid citation IDs and expected-symbol citation overlap are structural/proxy checks: neither proves that a claim follows from its cited source. The report leaves manual correctness and faithfulness fields ungraded for explicit review. Strict attack-marker detection flags even explanatory quotations and needs contextual review.

Results should be discussed with case counts, failure examples, and limitations. This small single run cannot establish general accuracy, confidence under distribution shift, or a bank's Responsible AI compliance. No parameter tuning is performed after inspecting this run.
