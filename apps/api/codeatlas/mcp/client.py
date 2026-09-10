"""Fixed stdio transport; discovery never grants additional model capabilities."""

import json
import os
import sys
from pathlib import Path

import anyio
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client

from codeatlas.core.errors import DomainError
from codeatlas.mcp.contracts import MAX_RESULT_BYTES, PREFIX, RESULTS, TOOLS, Envelope

TIMEOUT_SECONDS = 15


async def exchange(parameters, action, arguments):
    # Only the bundled server is launched. Never accept a model-supplied command or URL.
    with open(os.devnull, "w") as errors:
        with anyio.fail_after(TIMEOUT_SECONDS):
            async with Client(
                stdio_client(parameters, errlog=errors), read_timeout_seconds=TIMEOUT_SECONDS
            ) as client:
                discovery = await client.list_tools()
                if {tool.name for tool in discovery.tools} != {PREFIX + name for name in TOOLS}:
                    raise DomainError("mcp_discovery_failed", "Unexpected MCP tool registry.", 502)
                response = await client.call_tool(PREFIX + action, {"arguments": arguments})
                if response.is_error:
                    raise DomainError("mcp_tool_failed", "MCP tool rejected the request.", 502)
                return response.structured_content


class MCPReadTools:
    def __init__(self, reader, settings):
        self.reader = reader
        self.parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "codeatlas.mcp.server", "--repository", reader.repository.id],
            cwd=str(Path(__file__).resolve().parents[2]),
            env={"CODEATLAS_DATABASE_URL": settings.database_url.get_secret_value()},
        )

    def execute(self, action, arguments):
        if action not in TOOLS:
            raise DomainError(
                "tool_not_allowed", "MCP permits only registered snapshot reads.", 422
            )
        try:
            parsed = TOOLS[action].model_validate(arguments)
        except ValueError as exc:
            raise DomainError("invalid_tool_arguments", "Invalid MCP tool arguments.", 422) from exc
        try:
            data = anyio.run(exchange, self.parameters, action, parsed.model_dump())
        except DomainError:
            raise
        except Exception as exc:
            raise DomainError(
                "mcp_unavailable", "MCP read failed or timed out. Check the local server.", 502
            ) from exc
        return self.accept(action, parsed.model_dump(), data)

    def accept(self, action, arguments, data):
        try:
            if len(json.dumps(data, ensure_ascii=False).encode()) > MAX_RESULT_BYTES:
                raise ValueError("Oversized result")
            envelope = Envelope.model_validate(data)
            if envelope.repository_id != self.reader.repository.id:
                raise ValueError("Wrong snapshot")
            if envelope.error:
                if envelope.result is not None or envelope.evidence:
                    raise ValueError("Ambiguous result")
                # Do not reflect arbitrary server-provided error text to the model or UI.
                raise DomainError(
                    "mcp_read_failed", "MCP could not read the requested snapshot data.", 502
                )
            result = RESULTS[action].model_validate(envelope.result).model_dump()
            if action == "read_file":
                if len(envelope.evidence) != 1:
                    raise ValueError("Missing evidence")
                citation = envelope.evidence[0]
                file = self.reader.file(arguments["file_id"])
                lines = file.source.split("\n")
                if (
                    citation.file_id != file.id
                    or citation.file_path != file.path
                    or citation.start_line != arguments["start_line"]
                    or not citation.start_line <= citation.end_line <= arguments["end_line"]
                    or citation.end_line > len(lines)
                    or len(citation.source.encode()) > 6000
                    or citation.source
                    != "\n".join(
                        line.removesuffix("\r")
                        for line in lines[citation.start_line - 1 : citation.end_line]
                    )
                    or result["excerpt"] != citation.model_dump(exclude={"source"})
                ):
                    raise ValueError("Invalid evidence")
                citation = self.reader.remember(citation)
                result["excerpt"] = citation.model_dump(exclude={"source"})
            else:
                if envelope.evidence:
                    raise ValueError("Unexpected evidence")
                items = result.get("files", result.get("symbols", []))
                if action == "inspect_dependencies":
                    if result["file_id"] != arguments["file_id"]:
                        raise ValueError("Wrong file")
                    self.reader.file(result["file_id"])
                    items = result["imports"] + result["imported_by"]
                for item in items:
                    if self.reader.file(item["file_id"]).path[:200] != item["path"]:
                        raise ValueError("Invalid file reference")
            return result
        except DomainError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise DomainError(
                "mcp_invalid_result", "MCP returned an invalid read result.", 502
            ) from exc
