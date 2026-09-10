"""Container boundary with bounded output and cleanup; never execute repository code on host."""

import json
import os
import re
import selectors
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from codeatlas.core.errors import DomainError

PROFILES = {
    "python-unittest": (
        "codeatlas-sandbox-python:v1",
        ["python", "-I", "-B", "/opt/codeatlas/unittest_runner.py"],
    ),
    "node-test": ("codeatlas-sandbox-node:v1", ["node", "/opt/codeatlas/node_runner.mjs"]),
}
MAX_OUTPUT = 32_768
HOST_TIMEOUT = 35


@dataclass
class Outcome:
    status: str
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    error_code: str | None = None


def clean_output(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    text = re.sub(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))", "", text)
    return "".join(c for c in text if c in "\n\t" or c.isprintable())


def docker_command(args, timeout=5):
    try:
        return subprocess.run(["docker", *args], capture_output=True, timeout=timeout, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise DomainError(
            "sandbox_unavailable",
            "Docker or the trusted sandbox image is unavailable. See sandbox setup.",
            503,
        ) from exc


def require_sandbox(settings, profile):
    if not settings.sandbox_enabled:
        raise DomainError(
            "sandbox_disabled",
            "Enable CODEATLAS_SANDBOX_ENABLED on the server after building the sandbox images.",
            503,
        )
    if profile not in PROFILES:
        raise DomainError("invalid_test_profile", "Choose a supported test profile.", 422)
    # Resolve the trusted tag once, then use its immutable local image ID. Never pull at runtime.
    tag = PROFILES[profile][0]
    image = docker_command(["image", "inspect", "--format", "{{.Id}}", tag]).stdout.decode().strip()
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
        raise DomainError(
            "invalid_sandbox_image", "The trusted sandbox image could not be resolved.", 503
        )
    return image


def create_arguments(name: str, source: Path, profile: str, image_id: str):
    # Mount only the temporary source directory; never sockets, .env or a checkout.
    if "," in str(source):
        raise DomainError(
            "sandbox_path_invalid", "Sandbox workspace root cannot contain commas.", 422
        )
    return [
        "create",
        "--name",
        name,
        "--pull=never",
        "--network=none",
        "--read-only",
        "--user=65534:65534",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--memory=256m",
        "--memory-swap=256m",
        "--cpus=1",
        "--pids-limit=64",
        "--ulimit=nofile=256:256",
        "--ulimit=fsize=8388608:8388608",
        "--shm-size=16m",
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777",
        "--log-driver=none",
        "--label=codeatlas.sandbox=v1",
        "--workdir=/workspace",
        "--env=HOME=/tmp",
        "--mount",
        f"type=bind,src={source},dst=/workspace,readonly",
        "--entrypoint=/usr/bin/timeout",
        image_id,
        "--signal=KILL",
        "30s",
        *PROFILES[profile][1],
    ]


def run_container(source: Path, profile: str, image_id: str) -> Outcome:
    name = "codeatlas-test-" + uuid4().hex
    process = None
    result = None
    try:
        docker_command(create_arguments(name, source, profile, image_id))
        process = subprocess.Popen(
            ["docker", "start", "--attach", name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        )
        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        deadline = time.monotonic() + HOST_TIMEOUT
        status = None
        with selectors.DefaultSelector() as selector:
            for stream, key in [(process.stdout, "stdout"), (process.stderr, "stderr")]:
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, key)
            while selector.get_map():
                if time.monotonic() >= deadline:
                    status = "timeout"
                    break
                for key, _ in selector.select(timeout=0.1):
                    data = os.read(key.fd, 4096)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    available = MAX_OUTPUT - sum(len(value) for value in buffers.values())
                    buffers[key.data].extend(data[:available])
                    if len(data) > available:
                        status = "output_limit"
                        break
                if status:
                    break
        if status:
            result = Outcome(status, None, error_code="test_" + status)
        else:
            process.wait(timeout=max(0.1, deadline - time.monotonic()))
            # Inspect actual container state, not the Docker client's exit code or test output.
            state = json.loads(
                docker_command(["inspect", "--format", "{{json .State}}", name]).stdout
            )
            if state["Running"] or state["Error"]:
                result = Outcome("error", None, error_code="sandbox_start_failed")
            else:
                code = int(state["ExitCode"])
                status = (
                    "passed"
                    if code == 0
                    else "timeout"
                    if code in (124, 137) and not state["OOMKilled"]
                    else "failed"
                )
                result = Outcome(
                    status, code, error_code="test_timeout" if status == "timeout" else None
                )
        if result.status != "error":
            result.stdout = clean_output(bytes(buffers["stdout"]))
            result.stderr = clean_output(bytes(buffers["stderr"]))
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, DomainError):
        result = Outcome("error", None, error_code="sandbox_unavailable")
    finally:
        # PID 1 timeout bounds execution even if the API dies or Docker disconnects.
        try:
            docker_command(["rm", "--force", name])
        except DomainError:
            result = Outcome("error", None, error_code="sandbox_cleanup_failed")
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=2)
            process.stdout.close()
            process.stderr.close()
    return result
