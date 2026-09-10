# Claude and MCP in CodeAtlas

Status: Claude reasoning adapter implemented; MCP client/server integration proposed.

```text
                   Claude Messages API
                           ^
                    decisions / observations
                           v
                CodeAtlas agent runtime
          validation, permissions, budgets, trace
                  /                     \
          Local Python tools        MCP client (planned)
                                         |
                                 MCP server(s) (planned)
                                  /       |       \
                             Git reads  Repo DB  Testing
                                                   |
                                          Existing Docker sandbox
```

The runtime is the host application. Claude proposes an action; the runtime decides whether it is permitted, calls a local handler or an MCP tool, bounds the result, records it, and includes the observation in the next model request. MCP standardizes the client/server tool interface; it does not provide the reasoning model, authorization policy, or execution sandbox. See the official [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture).

A single CodeAtlas MCP server could expose all three services. Separate servers are also possible, with a client connection for each. Local tools do not have to pass through MCP. Avoid exposing duplicate local/MCP versions of the same tool to the model without a reason.

## First integration scope

Begin with a local, read-only repository server: bounded file listing, exact symbol lookup, source reads, and dependency inspection backed by existing scoped services. The server must independently enforce the selected repository boundary. Do not expose raw SQL, arbitrary paths, shell commands, or unrestricted network requests. Semantic search can follow using the separately configured embedding service.

The client should map explicitly approved, namespaced tool names to existing application actions, validate arguments and returned data, enforce time/output limits, and persist sanitized tool outcomes in the run trace. Server discovery must not automatically grant every advertised capability. Source text and tool descriptions/results are untrusted input. Confirm SDK/client protocol compatibility before implementation.

Testing is a later capability: preserve explicit per-run profile authorization, current-diff review, workspace digest checks, the global three-attempt limit, fixed image/command selection, and Docker isolation. Passing testing through MCP must not grant host execution. Git reads can expose scoped metadata; commits, pushes, and PR creation require a separately defined write workflow. The current imported snapshot is not a complete Git checkout.

## Model and retrieval calls today

- Answers and agent decisions: Anthropic Messages API, default `claude-sonnet-5`, server key `CODEATLAS_ANTHROPIC_API_KEY`.
- Source/query embeddings: OpenAI embedding endpoint, default `text-embedding-3-small`, separate server key `CODEATLAS_OPENAI_API_KEY`.
- Graph construction: deterministic parsers and import resolution, no model call.
- Local tool execution: application Python code; approved test execution uses Docker.

An Anthropic key alone enables file/symbol/dependency investigation and drafts. RAG questions and semantic search also require embeddings and a ready index. `GET /index` exposes separate reasoning and embedding availability; it never returns secrets. Existing `configured` and `provider` fields describe embeddings for compatibility.

Configure `CODEATLAS_REASONING_PROVIDER=anthropic`. Omit `CODEATLAS_ANSWER_MODEL` for the provider default, or set a compatible Claude model explicitly. An existing GPT model override must be removed or replaced when switching. `openai` remains an explicit reasoning option; there is no automatic cross-provider fallback.

Mocked API and scripted control-flow tests establish integration mechanics. They do not establish live model quality, prompt-injection resistance across arbitrary inputs, or MCP interoperability. Those need separate live evaluations after each capability is connected.
