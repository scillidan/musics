"""Extract per-track credits from the cumaean site table into credits.json.

CUMAEAN_META points to the site script.js; a fallback .env (cwd, then repo
root) can define it. Writes cumaean/metadata/credits.json.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.common import PROJECT_ROOT, load_dotenv

load_dotenv(Path(".env"), PROJECT_ROOT / ".env")

if "CUMAEAN_META" not in os.environ:
    raise SystemExit(
        "Error: CUMAEAN_META is not set (env or .env: path to the site script.js)"
    )

SCRIPT_PATH = Path(os.environ["CUMAEAN_META"])
SOURCE_ROOT = Path(
    os.environ.get("CUMAEAN_SOURCE", r"C:\Users\User\Local\Media\cdn_media_cumaean")
)
OUT_PATH = (
    Path(__file__).resolve().parent.parent / "cumaean" / "metadata" / "credits.json"
)

TABLE_RE = re.compile(r"var table = \[(.*?)\n\];", re.S)
ROW_RE = re.compile(
    r'\{tit:"((?:[^"\\]|\\.)*)",\s*art:"((?:[^"\\]|\\.)*)",\s*'
    r'play:"((?:[^"\\]|\\.)*)",\s*src:"((?:[^"\\]|\\.)*)",\s*'
    r'cr:"((?:[^"\\]|\\.)*)"\}'
)
OGG_RE = re.compile(r"main/([^\"]+\.ogg)")
ANCHOR_RE = re.compile(r'<a href="([^"]+)"[^>]*>([^<]*)</a>')


def unescape_js(s: str) -> str:
    return s.replace('\\"', '"').replace("\\\\", "\\")


def parse_rows(text: str) -> dict[str, dict]:
    table = TABLE_RE.search(text)
    if not table:
        raise SystemExit("Error: could not find 'var table = [...]' in script.js")
    credits: dict[str, dict] = {}
    for m in ROW_RE.finditer(table.group(1)):
        tit, art, play, src, cr = (unescape_js(g) for g in m.groups())
        ogg = OGG_RE.search(play)
        if not ogg:
            print(f"Warning: no .ogg URL in row {tit!r}, skipped")
            continue
        stem = Path(ogg.group(1)).stem
        entry: dict[str, str] = {}
        if art:
            entry["artist"] = art
        lic = ANCHOR_RE.search(cr)
        if lic:
            entry["license-url"] = lic.group(1)
            entry["license"] = lic.group(2).strip()
        source = ANCHOR_RE.search(src)
        if source:
            entry["source-url"] = source.group(1)
        key = stem.lower()
        if key in credits:
            print(f"Warning: duplicate entry for {stem!r}, keeping first")
            continue
        credits[key] = entry
    return credits


def main() -> int:
    if not SCRIPT_PATH.is_file():
        print(f"Error: {SCRIPT_PATH} not found")
        return 1
    credits = parse_rows(SCRIPT_PATH.read_text(encoding="utf-8"))
    print(f"Parsed {len(credits)} rows from {SCRIPT_PATH.name}")

    sources = (
        {
            p.stem.lower()
            for p in SOURCE_ROOT.iterdir()
            if p.is_file() and p.suffix.lower() == ".ogg"
        }
        if SOURCE_ROOT.is_dir()
        else set()
    )

    matched = sources & credits.keys()
    print(f"Matched {len(matched)}/{len(sources)} source tracks")
    missing = sorted(sources - credits.keys())
    if missing:
        print("Sources without credits:")
        for s in missing:
            print(f"  {s}")
    unused = sorted(set(credits) - sources)
    if unused:
        print("Credits without source file:")
        for s in unused:
            print(f"  {s}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(credits, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
