"""
cli.py — Entry point for the `ahc build` compiler CLI.

Usage:
    ahc build <manifest.yaml> [--output <dir>]

The compiler loads and validates a World Manifest YAML file, then emits
deterministic runtime artifacts to the output directory.

Same manifest → same artifacts. Always.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from compiler.loader import load, ManifestValidationError
from compiler.emitter import emit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ahc",
        description="Agent Hypervisor Compiler — build a World Manifest into runtime artifacts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser(
        "build",
        help="Compile a World Manifest YAML into deterministic runtime artifacts.",
    )
    build_parser.add_argument(
        "manifest",
        metavar="MANIFEST",
        help="Path to the World Manifest YAML file.",
    )
    build_parser.add_argument(
        "--output",
        "-o",
        metavar="DIR",
        default=None,
        help=(
            "Output directory for compiled artifacts. "
            "Defaults to 'compiled/<manifest-name>/' next to the manifest file."
        ),
    )
    build_parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress output except for errors.",
    )

    args = parser.parse_args(argv)

    if args.command == "build":
        return _cmd_build(args)

    parser.print_help()
    return 1


def _cmd_build(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)

    # Load and validate
    if not args.quiet:
        print(f"Loading manifest: {manifest_path}")

    try:
        manifest = load(manifest_path)
    except ManifestValidationError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    manifest_name = manifest["manifest"]["name"]

    # Resolve output directory
    if args.output:
        output_dir = Path(args.output)
    else:
        output_dir = manifest_path.parent / "compiled" / manifest_name

    if not args.quiet:
        print(f"Compiling '{manifest_name}' → {output_dir}/")

    # Emit artifacts
    try:
        written = emit(manifest, output_dir)
    except Exception as e:
        print(f"ERROR during emission: {e}", file=sys.stderr)
        return 1

    if not args.quiet:
        for filename, path in sorted(written.items()):
            print(f"  ✓ {path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path}")
        print(f"\nBuild complete. {len(written)} artifact(s) written.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
