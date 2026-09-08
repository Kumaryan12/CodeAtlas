import json
import os
import subprocess
import sys
from pathlib import Path

from codeatlas.core.errors import DomainError
from codeatlas.ingestion.archive import ScanLimits
from codeatlas.parsers.types import ScanResult


def analyze(workspace: Path, limits: ScanLimits, timeout: int) -> ScanResult:
    (workspace / "limits.json").write_text(limits.model_dump_json())
    try:
        # Fixed command and trusted module. -I ignores PYTHONPATH and the current directory.
        # A separate process lets us terminate a pathological parser, including native code.
        subprocess.run(
            [sys.executable, "-I", "-m", "codeatlas.ingestion.worker", str(workspace)],
            cwd=Path(__file__).resolve().parents[2],
            env={key: value for key, value in os.environ.items() if key in {"PATH", "SYSTEMROOT"}},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=True,
        )
        payload = json.loads((workspace / "result.json").read_text(encoding="utf-8"))
    except subprocess.TimeoutExpired as exc:
        raise DomainError(
            "analysis_timeout", "Source analysis exceeded its time limit.", 504
        ) from exc
    except (subprocess.CalledProcessError, OSError, ValueError) as exc:
        raise DomainError(
            "analysis_failed", "The source parser could not finish this repository.", 422
        ) from exc
    if "error" in payload:
        raise DomainError(**payload["error"])
    return ScanResult.model_validate(payload["result"])
