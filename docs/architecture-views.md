# Dependency and Data Flow views

Open a completed snapshot, choose **Architecture**, then select **Dependencies** or **Data Flow**. Both views reuse stored snapshot data: no reimport, embeddings, API key, or LLM call is required.

## Arrow meanings

**Dependencies**: A → B means file A imports file B. Each edge retains import evidence. These arrows describe code structure, not processing order.

**Data Flow**: A → B means a supported static Python expression passes a value returned by a function associated with A into a function defined in B. For example:

```python
from .data import load
from .model import train

rows = load()
train(rows)
```

The dependency edges are `main.py → data.py` and `main.py → model.py`. The data-flow edge is `data.py → model.py`, with the `train(rows)` call-site location in `main.py`. Select either endpoint to inspect evidence and open the call-site file. A source line is shown for manual inspection; the source viewer opens the file rather than automatically navigating to that line.

In the saved F1 snapshot, the supported pipeline segment is `data.py → features.py → model.py`, coordinated in `main.py`. Additional edges can connect returned model/features values to helpers in `main.py`. This is an analysis of potential value passing; it does not establish execution order, branch reachability, or complete lineage.

## How analysis works

The read-only `GET /api/repositories/{id}/graph?view=data_flow` endpoint reads source scoped to the selected snapshot. Python AST parsing extracts top-level functions and resolves supported named function imports/module aliases using the existing local import resolver. The analyzer tracks assignments, nested/keyword calls, and return summaries for local helpers, recording producer-to-consumer file edges at call sites. Branch-local calls are included as potential flow; variable provenance survives a branch join only when both branch environments agree. Reassignment invalidates previous origins.

The normal `/graph` endpoint and `?view=dependency` retain their existing dependency semantics. Neither RAG's dependency expansion nor MCP dependency inspection silently switches to the new view.

Analysis is bounded to 100 Python files, 2 MB of Python source, 30,000 AST nodes per file, eight summary passes, 300,000 analysis steps, and a checked five-second work budget. The deadline is cooperative, not an OS-enforced hard timeout. Truncation/parse failures are reported in coverage notes; excessive analysis work returns a controlled error. Each file-pair edge retains up to 20 call-site observations; the UI previews three. Cycles are grouped for layout and labelled as flow cycles rather than import cycles.

## Explicit limitations

This first version supports **Python only**. JavaScript/TypeScript files remain visible but their data flow is not analyzed. It does not model class methods, dynamic dispatch, mutation, argument-to-return forwarding, external library calls, asynchronous await provenance, complex loops/try/with blocks, or arbitrary aliasing. Unsupported calls do not act as presumed passthroughs. Source is parsed, never imported or executed.

No arrow does not prove that two files exchange no data. Arrows are not a runtime trace or an LLM's inferred architecture. A complete lineage system would need richer interprocedural analysis and/or deliberately instrumented, isolated execution.

## Verification

Regression cases cover return-to-argument direction versus imports, local helper returns, nested and keyword calls, module aliases, branch joins, overwritten/shadowed functions and values, parse failures, and non-execution of source. API integration checks validate source-scoped call-site evidence, repository isolation, invalid view rejection, and unchanged dependency defaults. Live HTTP checks use the existing F1 snapshot and frontend proxy. Browser automation was unavailable, so visual interaction has not been verified in this session.
