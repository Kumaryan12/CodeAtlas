"""Trusted parser entry point. Input source is data; it is never imported or executed."""

import json
import sys
from pathlib import Path

from codeatlas.core.errors import DomainError
from codeatlas.ingestion.archive import ScanLimits, scan_archive


def main() -> None:
    workspace = Path(sys.argv[1])
    limits = ScanLimits.model_validate_json((workspace / "limits.json").read_text())
    try:
        result = scan_archive(workspace / "repository.tar.gz", workspace, limits)
        payload = {"result": result.model_dump()}
    except DomainError as exc:
        payload = {
            "error": {"code": exc.code, "message": exc.message, "status_code": exc.status_code}
        }
    (workspace / "result.json").write_text(json.dumps(payload), encoding="utf-8")


if __name__ == "__main__":
    main()
