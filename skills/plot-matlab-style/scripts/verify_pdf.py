#!/usr/bin/env python3
"""Verify PDF page size and embedded fonts with Poppler utilities."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path


PAGE_RE = re.compile(r"Page size:\s+([0-9.]+) x ([0-9.]+) pts")


def command_output(command: list[str]) -> str:
    return subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ).stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--width", type=float, required=True)
    parser.add_argument("--height", type=float, required=True)
    parser.add_argument("--tolerance", type=float, default=0.05)
    args = parser.parse_args()

    for command in ("pdfinfo", "pdffonts"):
        if shutil.which(command) is None:
            raise SystemExit(f"missing required command: {command}")
    if not args.pdf.is_file():
        raise SystemExit(f"PDF not found: {args.pdf}")

    info = command_output(["pdfinfo", str(args.pdf)])
    match = PAGE_RE.search(info)
    if match is None:
        raise SystemExit("could not parse PDF page size")
    width, height = map(float, match.groups())
    if abs(width - args.width) > args.tolerance or abs(height - args.height) > args.tolerance:
        raise SystemExit(
            f"page size {width:g} x {height:g} pt; "
            f"expected {args.width:g} x {args.height:g} pt"
        )

    fonts = command_output(["pdffonts", str(args.pdf)])
    rows = [line for line in fonts.splitlines()[2:] if line.strip()]
    if not rows:
        raise SystemExit("PDF has no detectable embedded fonts")
    unembedded = [line for line in rows if not re.search(r"\byes\s+yes\b", line)]
    if unembedded:
        raise SystemExit("one or more PDF fonts are not embedded/subset")

    print(f"OK: {args.pdf} ({width:g} x {height:g} pt, {len(rows)} font subsets)")


if __name__ == "__main__":
    main()
