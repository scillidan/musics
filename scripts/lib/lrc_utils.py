"""Common utilities for LRC (LyRiCs) files."""

from __future__ import annotations

import re
from pathlib import Path

LRC_TIME_RE = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)")


def parse_timestamp(ts: str) -> float:
    """Parse an LRC timestamp like '01:23.45' into seconds."""
    minutes, seconds = ts.split(":")
    return int(minutes) * 60 + float(seconds)


def format_timestamp_srt(seconds: float) -> str:
    """Format seconds as SRT time 'HH:MM:SS,mmm'."""
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_timestamp_lrc(seconds: float) -> str:
    """Format seconds as LRC timestamp '[MM:SS.mm]'."""
    minutes = int(seconds) // 60
    secs = seconds % 60
    return f"[{minutes:02d}:{secs:05.2f}]"


def parse_lrc(path: Path) -> list[tuple[float, str]]:
    """Parse an LRC file into (timestamp, text) pairs."""
    lines: list[tuple[float, str]] = []
    if not path.exists():
        return lines

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            m = LRC_TIME_RE.match(line)
            if not m:
                continue
            try:
                ts = parse_timestamp(f"{m.group(1)}:{m.group(2)}")
            except ValueError:
                continue
            text = m.group(3).strip()
            lines.append((ts, text))
    return lines


def strip_timestamps(text: str) -> str:
    """Remove LRC timestamps from the start of each line."""
    return "\n".join(LRC_TIME_RE.sub("", line).strip() for line in text.splitlines())
