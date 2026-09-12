"""Opt-in real Docker checks. Never execute these fixture programs on the host."""

import os

import pytest

from codeatlas.core.config import Settings
from codeatlas.sandbox import docker

pytestmark = pytest.mark.skipif(
    os.environ.get("CODEATLAS_TEST_DOCKER") != "1", reason="Opt-in Docker sandbox integration"
)


def run(tmp_path, files, profile="python-unittest"):
    tmp_path.chmod(0o755)
    for name, source in files.items():
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(source)
    image = docker.require_sandbox(Settings(_env_file=None, sandbox_enabled=True), profile)
    return docker.run_container(tmp_path.resolve(), profile, image)


def test_real_python_restrictions_and_output(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEATLAS_SANDBOX_SECRET_SENTINEL", "must-not-enter-container")
    result = run(
        tmp_path,
        {
            "test_boundary.py": """
import os
import pathlib
import socket
import unittest
class Boundary(unittest.TestCase):
    def test_isolation(self):
        self.assertEqual(os.getuid(), 65534)
        self.assertNotIn("CODEATLAS_SANDBOX_SECRET_SENTINEL", os.environ)
        self.assertFalse(pathlib.Path("/var/run/docker.sock").exists())
        self.assertFalse(pathlib.Path("/workspace/.env").exists())
        with self.assertRaises(OSError):
            pathlib.Path("/workspace/changed.py").write_text("bad")
        with self.assertRaises(OSError):
            pathlib.Path("/etc/changed").write_text("bad")
        pathlib.Path("/tmp/allowed").write_text("temporary")
        with socket.socket() as sock:
            sock.settimeout(.2)
            self.assertNotEqual(sock.connect_ex(("1.1.1.1", 443)), 0)
        status = pathlib.Path("/proc/self/status").read_text()
        self.assertIn("CapEff:\\t0000000000000000", status)
        self.assertIn("NoNewPrivs:\\t1", status)
        self.assertIn("Seccomp:\\t2", status)
        self.assertEqual(pathlib.Path("/sys/fs/cgroup/memory.max").read_text().strip(), "268435456")
        self.assertEqual(pathlib.Path("/sys/fs/cgroup/pids.max").read_text().strip(), "64")
        print("isolation verified")
"""
        },
    )
    assert result.status == "passed", result
    assert "isolation verified" in result.stdout and "Ran 1 test" in result.stderr
    assert not (tmp_path / "changed.py").exists()


def test_real_node_typescript(tmp_path):
    result = run(
        tmp_path,
        {
            "sum.test.ts": 'import { test } from "node:test";\n'
            'import assert from "node:assert/strict";\nconst value: number = 4;\n'
            'test("sum", () => assert.equal(value, 4));\n'
        },
        "node-test",
    )
    assert result.status == "passed" and "# pass 1" in result.stdout, result


def test_real_failure_and_no_tests(tmp_path):
    result = run(tmp_path, {})
    assert result.status == "failed" and result.exit_code == 5
    result = run(
        tmp_path,
        {
            "test_failure.py": "import unittest\nclass Failure(unittest.TestCase):\n"
            " def test_failure(self): self.assertEqual(1,2)\n"
        },
    )
    assert result.status == "failed" and result.exit_code == 1
    assert "AssertionError" in result.stderr


@pytest.mark.parametrize("stream", [1, 2])
def test_real_output_limit(tmp_path, stream):
    result = run(
        tmp_path, {"test_flood.py": f'import os\nwhile True: os.write({stream}, b"x" * 4096)\n'}
    )
    assert result.status == "output_limit", result
    assert len(result.stdout) + len(result.stderr) <= docker.MAX_OUTPUT


def test_real_timeout(tmp_path):
    result = run(tmp_path, {"test_loop.py": "while True: pass\n"})
    assert result.status == "timeout", result


def test_no_sandbox_containers_remain():
    result = docker.docker_command(["ps", "-aq", "--filter", "label=codeatlas.sandbox=v1"])
    assert not result.stdout.strip()
