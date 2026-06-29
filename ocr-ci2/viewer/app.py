"""Severity Dashboard — deprecated standalone entry; use Gateway :8010."""

from __future__ import annotations

import argparse
import os
import sys
import warnings

from gateway.main import app  # noqa: F401


def main() -> None:
    warnings.warn(
        "Standalone Severity Dashboard (:5484) is deprecated. "
        "Start OCR Gateway instead: .\\deploy\\local\\run.ps1 (Dashboard at http://localhost:8010/)",
        DeprecationWarning,
        stacklevel=1,
    )
    parser = argparse.ArgumentParser(description="OCR Severity Dashboard (deprecated)")
    parser.add_argument("--host", default=os.environ.get("SEVERITY_VIEWER_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("SEVERITY_VIEWER_PORT", "5484")),
    )
    args = parser.parse_args()

    import uvicorn

    uvicorn.run("gateway.main:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
