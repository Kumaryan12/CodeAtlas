# Five-minute CodeAtlas demo

## Before the interview

1. Start Docker/PostgreSQL, the API and frontend using the README. Preserve `.env`; never display keys.
2. Open an existing F1 snapshot and check that both Architecture views load. Import a repository ahead of time if needed.
3. Build the local semantic index ahead of time if you will show Ask. First-time model download/indexing is setup, not the demo.
4. Open the saved repair evidence and patch. Label these as recorded runs. Live calls can fail and are optional.
5. Practise once in a real browser. Automated visual verification was unavailable during development; do not assume every interaction has been checked.

## 0:00–0:45 — problem and snapshot

“Developers need to understand unfamiliar code and inspect proposed changes. CodeAtlas grounds its analysis in a saved repository commit.”

Open the source explorer. Show a file, a symbol, and the pinned commit. Explain that source parsing does not execute imported code.

## 0:45–1:45 — two architecture views

Open Architecture → Dependencies. Point out that the arrow means **imports**.

Switch to Data Flow. In F1, show the supported `data.py → features.py → model.py` segment and inspect the call-site evidence in `main.py`. Explain that this is a bounded static Python analysis, not a runtime trace. Toggle **Show unconnected files** to explain that missing flow may also mean unsupported analysis.

## 1:45–2:30 — retrieval and answers

In Ask, use a specific question about a function visible in the snapshot. Preview the retrieved context before asking Claude. Open a citation and compare the claim to the source.

Explain the separation: local embeddings select candidate evidence; Claude generates the answer. If the model times out, show the recorded result honestly instead of presenting a fallback as a successful live call.

## 2:30–4:00 — controlled repair

Show a recorded readiness run from `docs/evaluation-repair-readiness/`:

- Original `normalize_email()` strips whitespace but does not lowercase.
- Original sandbox tests fail the normalization assertion.
- Agent inspects source, changes only `auth.py`, reviews the diff, and runs approved tests.
- The final draft passes the original tests; an independent run verifies them again.
- Stored source remains unchanged. Nothing is applied upstream.

For an optional live reproduction, use:

```sh
apps/api/.venv/bin/python -m codeatlas.evaluation.repair --live --output /tmp/codeatlas-demo.json
```

This uses Claude and real Docker, and may incur provider charges. It operates on an isolated synthetic fixture, not a user's working repository. A nonzero exit means a required check failed; inspect the artifact.

## 4:00–5:00 — evidence and judgment

Show the readiness report and CI link. Explain:

- Hybrid Recall@6 is 98.1% on 18 positively labelled synthetic questions; that is not answer accuracy.
- Graph expansion reduced coverage on this small corpus, so its benefit is not assumed.
- A final-response bug was caused by empty citations on draft/test claims. Clarifying the finish contract recovered the demonstrated workflow without weakening validation.
- Accepted citation IDs do not prove entailment; qualitative review still identifies limitations.

Finish by identifying the next engineering priorities: broader independently reviewed cases, provider reliability, claim-level support, and production operation if the scope grows.
