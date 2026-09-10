"""A local stdio server fixed to one snapshot; no model keys or execution tools."""

import argparse
import logging
import os
from uuid import UUID

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from codeatlas.agents.tools import FileId, ListFiles, ReadFile, ReadTools, SearchCode
from codeatlas.core.errors import DomainError
from codeatlas.mcp.contracts import MAX_RESULT_BYTES, PREFIX, Envelope, ToolFailure
from codeatlas.models.repository import Repository


def create_server(engine, repository_id: str) -> MCPServer:
    repository_id = str(UUID(repository_id))
    server = MCPServer("CodeAtlas snapshot reads", version="1.0.0", log_level="CRITICAL")

    def execute(action, arguments):
        try:
            with Session(engine) as session:
                repository = session.get(Repository, repository_id)
                if repository is None or repository.status not in {"ready", "partial"}:
                    raise DomainError("repository_unavailable", "Snapshot is unavailable.", 404)
                reader = ReadTools(session, repository, None, None)
                result = reader.execute(action, arguments.model_dump())
                envelope = Envelope(
                    repository_id=repository_id,
                    result=result,
                    evidence=list(reader.evidence.values()),
                )
                if len(envelope.model_dump_json().encode()) > MAX_RESULT_BYTES:
                    raise DomainError("mcp_output_limit", "MCP result exceeded its limit.", 502)
                return envelope
        except DomainError as exc:
            return Envelope(
                repository_id=repository_id, error=ToolFailure(code=exc.code, message=exc.message)
            )
        except Exception:
            # No DB URLs, source, raw exceptions, or credentials in protocol errors/logs.
            return Envelope(
                repository_id=repository_id,
                error=ToolFailure(code="mcp_server_failed", message="Snapshot read failed."),
            )

    annotations = ToolAnnotations(
        read_only_hint=True, destructive_hint=False, open_world_hint=False
    )

    @server.tool(name=PREFIX + "list_files", annotations=annotations)
    def list_files(arguments: ListFiles) -> Envelope:
        """List at most 20 source paths in the server's fixed snapshot."""
        return execute("list_files", arguments)

    @server.tool(name=PREFIX + "find_symbol", annotations=annotations)
    def find_symbol(arguments: SearchCode) -> Envelope:
        """Find up to 20 exact, case-sensitive symbol matches in the fixed snapshot."""
        return execute("find_symbol", arguments)

    @server.tool(name=PREFIX + "read_file", annotations=annotations)
    def read_file(arguments: ReadFile) -> Envelope:
        """Read up to 120 lines / 6000 bytes from a file in the fixed snapshot."""
        return execute("read_file", arguments)

    @server.tool(name=PREFIX + "inspect_dependencies", annotations=annotations)
    def inspect_dependencies(arguments: FileId) -> Envelope:
        """Inspect bounded static imports and importers in the fixed snapshot."""
        return execute("inspect_dependencies", arguments)

    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, type=UUID)
    args = parser.parse_args()
    # Deliberately do not load .env, Settings, or any AI credentials in this process.
    logging.disable(logging.CRITICAL)
    engine = None
    try:
        engine = create_engine(os.environ["CODEATLAS_DATABASE_URL"], pool_pre_ping=True)
        create_server(engine, str(args.repository)).run(transport="stdio")
    except Exception:
        raise SystemExit("CodeAtlas MCP server could not start.") from None
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    main()
