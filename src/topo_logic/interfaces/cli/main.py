"""CLI entrypoint (`topo-logic info`, `topo-logic serve`)."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from topo_logic import __version__
from topo_logic.infrastructure.config import AppSettings
from topo_logic.infrastructure.mesh import (
    CompositeGeometryImporter,
    GmshStepImporter,
    TrimeshSurfaceImporter,
)
from topo_logic.interfaces.api.app import create_app


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="topo-logic",
        description="Topo_Logic — Open-source 3D FEM & Topology Optimization CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("info", help="Show version, active adapters, and supported formats.")

    serve_parser = subparsers.add_parser("serve", help="Start the Topo_Logic FastAPI server.")
    serve_parser.add_argument("--host", default=None, help="Bind host (default: 127.0.0.1).")
    serve_parser.add_argument("--port", type=int, default=None, help="Bind port (default: 8000).")
    serve_parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Local runtime data directory for SQLite DB and artifacts.",
    )
    return parser


def _cmd_info(settings: AppSettings) -> int:
    importer = CompositeGeometryImporter([TrimeshSurfaceImporter(), GmshStepImporter()])
    formats = ", ".join(fmt.value.upper() for fmt in sorted(importer.supported_formats()))
    print(f"Topo_Logic {__version__}")
    print("Execution Mode : local_first (SQLite + LocalFS + Local Workers)")
    print(f"Data Directory : {settings.data_dir}")
    print(f"Formats        : {formats}")
    print(f"Default Server : http://{settings.host}:{settings.port}")
    return 0


def _cmd_serve(settings: AppSettings) -> int:
    app = create_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    settings = AppSettings()

    if args.command == "info":
        return _cmd_info(settings)

    if args.command == "serve":
        overrides: dict[str, object] = {}
        if args.host is not None:
            overrides["host"] = args.host
        if args.port is not None:
            overrides["port"] = args.port
        if args.data_dir is not None:
            overrides["data_dir"] = args.data_dir
        updated_settings = settings.model_copy(update=overrides) if overrides else settings
        return _cmd_serve(updated_settings)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
