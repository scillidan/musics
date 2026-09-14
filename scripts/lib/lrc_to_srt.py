"""Convert an LRC file to SRT format.

Usage:
    python lrc_to_srt.py <input.lrc> <output.srt>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lib.lrc_utils import format_timestamp_srt, parse_lrc


def lrc_to_srt(lrc_path: Path, srt_path: Path) -> None:
    lines = parse_lrc(lrc_path)
    if not lines:
        srt_path.write_text("", encoding="utf-8")
        return

    subs: list[str] = []
    for idx, (start, text) in enumerate(lines):
        if idx + 1 < len(lines):
            end = lines[idx + 1][0]
        else:
            end = start + 1.0
        subs.append(
            f"{idx + 1}\n"
            f"{format_timestamp_srt(start)} --> {format_timestamp_srt(end)}\n"
            f"{text}\n"
        )

    srt_path.write_text("\n".join(subs), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert LRC to SRT")
    parser.add_argument("input", type=Path, help="input LRC file")
    parser.add_argument("output", type=Path, help="output SRT file")
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        return 1

    lrc_to_srt(args.input, args.output)
    print(f"Converted '{args.input.name}' -> '{args.output.name}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
