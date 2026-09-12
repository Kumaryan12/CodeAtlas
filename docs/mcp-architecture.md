# Claude and MCP in CodeAtlas

Status: the bundled read-only MCP server and agent client are implemented. Claude reasoning is integrated and an initial [six-case live evaluation](evaluation-agent-live.md) is recorded. Broader model quality remains unverified.

```text
                   Claude Messages API
                           ^
                    decisions / observations
                           v
                CodeAtlas agent runtime
          validation, permissions, budgets, trace
                  /                     \
          Local Python tools        MCP client
          search / draft / tests         |
                                 Fixed stdio subprocess
                                         |
                               CodeAtlas snapshot server
                                         |
                            Scoped read services → Repo DB
```

The runtime is the host application. Claude proposes an action; the runtime validates it and routes four approved reads through MCP when enabled. The client discovers and checks the exact tool registry, calls the mapped namespaced tool, validates the response, and returns the observation to the model loop. The server independently scopes every query to its startup repository ID. Neither tool arguments nor model output can change that scope, launch another command, or select another server.

## Enable and demonstrate

Install the updated dependencies using the existing locked installation workflow:

```sh
apps/api/.venv/bin/pip install -r apps/api/requirements-dev.lock
apps/api/.venv/bin/pip install --no-deps -e 'apps/api[dev]'
```

Set `CODEATLAS_READ_TOOL_TRANSPORT=mcp` in the root `.env`, then restart the API. The example environment enables it; the Settings fallback is `local` for compatibility. Set `local` explicitly to use the original direct handlers. There is no silent fallback when MCP fails.

With the Anthropic key configured, start an investigation asking the agent to inspect a particular implementation. File, symbol, and dependency reads appear as **READ · MCP** in the trace. The trace's `transport` field records `mcp` or `local` independently of the action name, including failed reads. Existing traces without the field remain readable.

Without a model key, run the protocol and scripted-agent demonstration:

```sh
apps/api/.venv/bin/pytest apps/api/tests/test_mcp.py -q
```

This starts actual stdio subprocesses, performs all four reads, validates evidence, and checks a completed agent trace. Other tests exercise the real in-memory MCP protocol for hostile requests and malformed result handling. An unresponsive stdio subprocess is timed out and checked for termination.

## Tool contract

| MCP name | Arguments inside `arguments` | Bound |
| --- | --- | --- |
| `codeatlas_list_files` | `prefix`, `offset` | 20 source paths per page |
| `codeatlas_find_symbol` | `query` | 20 exact, case-sensitive symbol matches |
| `codeatlas_read_file` | `file_id`, `start_line`, `end_line` | 120 lines / 6000 bytes |
| `codeatlas_inspect_dependencies` | `file_id` | 10 imports and 10 importers |

For example, a tool call uses `{"arguments":{"prefix":"apps/","offset":0}}`. Discovery exposes typed schemas and read-only annotations. The annotations describe intent; fixed registration, strict argument validation, and scoped queries enforce the application boundary.

The server returns a bounded structured envelope with repository ID, result, and optional source evidence or sanitized error. The client checks response shape, snapshot identity, referenced file membership, and paths. For source evidence, it verifies the exact lines against the immutable local snapshot before allocating an agent-wide evidence ID. This preserves citation integrity across multiple MCP calls and local semantic search. Returned metadata alone does not establish a supported implementation claim.

Each call launches the bundled server, discovers its four tools, performs one read, and closes the connection/process. This costs process startup time but keeps lifecycle and scope explicit. The client limits connection/discovery/call work to 15 seconds; SDK cleanup may add a short termination grace period. Structured result envelopes are capped at 32 KB before the bundled server returns them and checked again by the client. Existing overall agent/tool/evidence budgets still apply.

## Standalone local server

An external local MCP host can launch the same server using:

```sh
apps/api/.venv/bin/python -m codeatlas.mcp.server --repository SNAPSHOT_UUID
```

Supply `CODEATLAS_DATABASE_URL` in that process's environment. The module does **not** load `.env`. Select an existing ready or partial snapshot UUID. Use an absolute Python executable path when configuring another host.

The runtime uses its own Python executable and fixed module/working directory. It passes only the database URL as application configuration, plus the SDK's minimal inherited platform environment. AI keys are not forwarded. No API key is needed by the read server.

This is trusted local application code with database access, not an OS-level database isolation boundary. The operator chooses the snapshot; remote authentication, multi-tenant authorization, and arbitrary third-party servers are not implemented. Do not deploy this stdio adapter as an unauthenticated remote database service. Imported source is treated as data and never executed by these tools.

## Protocol and remaining scope

The official [Python SDK](https://py.sdk.modelcontextprotocol.io/client/) is pinned to **2.2.0** in the lockfile; the bundled client/server pair is tested with MCP **2026-07-28**. Other external hosts and older protocol versions have not been interoperability-tested.

Search still uses the local embedding service. Draft edits and approved tests keep their existing local handlers and permissions. MCP does not expose Git writes, raw SQL, arbitrary paths, shell commands, remote URLs, editing, or Docker execution in this milestone. Later integrations must preserve the current approval, diff-review, workspace-digest, retry, and sandbox boundaries.

Claude answers and agent decisions use the separately configured reasoning provider. OpenAI source/query embeddings remain independent. Graph construction stays deterministic. MCP introduces no additional LLM call by itself.
