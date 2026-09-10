import copy
import sqlite3

import anyio
import pytest
from mcp import Client
from sqlalchemy.orm import Session
from test_agent import ScriptedInvestigator, decision, start
from test_qa import imported

from codeatlas.agents.tools import ReadTools
from codeatlas.core.errors import DomainError
from codeatlas.mcp.client import MCPReadTools
from codeatlas.mcp.contracts import PREFIX, TOOLS
from codeatlas.mcp.server import create_server
from codeatlas.models.repository import Repository


@pytest.fixture
def snapshot(api, fake_download, tmp_path):
    prefix = imported(api)
    other = imported(api)
    file = next(f for f in api.get(prefix + "/files").json()["items"] if f["path"] == "auth.py")
    foreign = api.get(other + "/files").json()["items"][0]["id"]
    path = tmp_path / "mcp.sqlite"
    with api.app.state.database.connect() as connection, sqlite3.connect(path) as target:
        connection.connection.driver_connection.backup(target)
    api.app.state.settings = type(api.app.state.settings)(
        _env_file=None, database_url=f"sqlite:///{path}", read_tool_transport="mcp"
    )
    return prefix, file["id"], foreign


def test_real_stdio_agent_reads_and_records_mcp_trace(api, snapshot):
    prefix, file_id, _ = snapshot
    provider = ScriptedInvestigator(
        [
            decision("list_files"),
            decision("find_symbol", {"query": "login"}),
            decision("inspect_dependencies", {"file_id": file_id}),
            decision("read_file", {"file_id": file_id, "start_line": 1, "end_line": 3}),
            decision(
                "finish",
                answer={
                    "status": "answered",
                    "claims": [{"text": "Login returns email.", "citation_ids": ["E1"]}],
                },
            ),
        ]
    )
    result = start(api, prefix, provider)
    assert result["status"] == "completed", result
    reads = [s for s in result["steps"] if s["kind"] == "read"]
    assert len(reads) == 4
    assert all(s["transport"] == "mcp" and s["status"] == "completed" for s in reads)
    assert "return email" in result["result"]["citations"][0]["source"]
    assert provider.states[-1]["evidence"][0]["id"] == "E1"


def test_server_discovery_and_scope_with_real_protocol(api, snapshot):
    prefix, file_id, foreign = snapshot
    server = create_server(api.app.state.database, prefix.rsplit("/", 1)[1])

    async def check():
        async with Client(server) as client:
            assert client.protocol_version == "2026-07-28"
            tools = (await client.list_tools()).tools
            assert {t.name for t in tools} == {PREFIX + name for name in TOOLS}
            assert all(t.annotations.read_only_hint for t in tools)
            good = await client.call_tool(
                PREFIX + "read_file",
                {"arguments": {"file_id": file_id, "start_line": 1, "end_line": 3}},
            )
            assert "return email" in good.structured_content["evidence"][0]["source"]
            bad = await client.call_tool(
                PREFIX + "read_file",
                {"arguments": {"file_id": foreign, "start_line": 1, "end_line": 3}},
            )
            assert bad.structured_content["error"]["code"] == "file_not_found"
            for name, args in [
                ("shell", {}),
                (PREFIX + "list_files", {"arguments": {"repository_id": "other"}}),
                (PREFIX + "list_files", {"arguments": {"offset": "0"}}),
                (
                    PREFIX + "read_file",
                    {"arguments": {"file_id": file_id, "start_line": 1, "end_line": 121}},
                ),
            ]:
                result = await client.call_tool(name, args)
                assert result.is_error

    anyio.run(check)


def test_client_validates_results_and_remaps_evidence(api, snapshot):
    prefix, file_id, foreign = snapshot
    with Session(api.app.state.database) as session:
        repository = session.get(Repository, prefix.rsplit("/", 1)[1])
        reader = ReadTools(session, repository, None, None)
        client = MCPReadTools(reader, api.app.state.settings)
        args = {"file_id": file_id, "start_line": 1, "end_line": 3}
        local = ReadTools(session, repository, None, None)
        data = {
            "repository_id": repository.id,
            "result": local.execute("read_file", args),
            "evidence": [c.model_dump() for c in local.evidence.values()],
        }
        reader.execute("read_file", {**args, "end_line": 1})
        result = client.accept("read_file", args, data)
        assert result["excerpt"]["id"] == "E2"
        assert client.accept("read_file", args, data)["excerpt"]["id"] == "E2"
        mutations = []
        bad = copy.deepcopy(data)
        bad["repository_id"] = "other"
        mutations.append(bad)
        bad = copy.deepcopy(data)
        bad["evidence"][0]["source"] = "fabricated"
        mutations.append(bad)
        bad = copy.deepcopy(data)
        bad["evidence"][0]["file_id"] = foreign
        mutations.append(bad)
        bad = copy.deepcopy(data)
        bad["result"] = {"unexpected": True}
        mutations.append(bad)
        bad = copy.deepcopy(data)
        bad["evidence"] = []
        mutations.append(bad)
        mutations += [None, {"padding": "x" * 32001}]
        for bad in mutations:
            with pytest.raises(DomainError) as error:
                client.accept("read_file", args, bad)
            assert error.value.code == "mcp_invalid_result"
        assert len(reader.evidence) == 2
        with pytest.raises(DomainError) as error:
            client.execute("run_tests", {})
        assert error.value.code == "tool_not_allowed"


def test_server_failure_becomes_failed_trace_without_local_fallback(api, snapshot, monkeypatch):
    prefix, _, _ = snapshot

    async def failure(*args):
        raise RuntimeError("private database credential")

    monkeypatch.setattr("codeatlas.mcp.client.exchange", failure)
    provider = ScriptedInvestigator(
        [
            decision("list_files"),
            decision("finish", answer={"status": "insufficient_context", "claims": []}),
        ]
    )
    result = start(api, prefix, provider)
    read = next(s for s in result["steps"] if s["kind"] == "read")
    assert read["transport"] == "mcp"
    assert read["status"] == "failed" and read["error_code"] == "mcp_unavailable"
    assert "private" not in read["summary"]
    assert "error" in provider.states[-1]["observations"][0]["result"]


def test_unresponsive_stdio_server_times_out_and_is_reaped(monkeypatch, tmp_path):
    import os
    import sys
    import time

    from mcp import StdioServerParameters

    from codeatlas.mcp.client import exchange

    pid_file = tmp_path / "child.pid"
    program = (
        "import os, pathlib, time; "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid())); time.sleep(30)"
    )
    monkeypatch.setattr("codeatlas.mcp.client.TIMEOUT_SECONDS", 0.5)
    parameters = StdioServerParameters(command=sys.executable, args=["-c", program])
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        anyio.run(exchange, parameters, "list_files", {})
    assert time.monotonic() - started < 5
    assert pid_file.exists()
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


def test_client_refuses_unexpected_discovery(monkeypatch):
    from types import SimpleNamespace

    from codeatlas.mcp.client import exchange

    class UnexpectedServer:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name="shell")])

        async def call_tool(self, *args):
            pytest.fail("Discovery must not grant execution")

    monkeypatch.setattr("codeatlas.mcp.client.Client", UnexpectedServer)
    with pytest.raises(DomainError) as error:
        anyio.run(exchange, None, "list_files", {})
    assert error.value.code == "mcp_discovery_failed"
