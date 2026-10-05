"""LRC preprocessor: strip non-lyric lines out of LRCs into metadata/ JSON files.

Run from a category dir (e.g. song/):

    uv run ../scripts/prep_lrc_meta.py            # apply changes
    uv run ../scripts/prep_lrc_meta.py --dry-run  # report only

For every .lrc under medias/ (including .zh-cn/.pinyin/.jyutping variants):

- credit/meta lines (作词/作曲/编曲/制作人/OP/ISRC/混音/录音/...) are removed
  from the LRC and saved into metadata/ JSON files keyed by English mp3-tag
  names. Names come from the glossary TSV (--glossary, "Music tag" and any
  other section); labels without a glossary entry become "others_<english>".
- title lines ("<title> - <artist>") are dropped (title is not needed).
- lyric lines are normalized to "[mm:ss.xx] <text>" (one space after the
  bracket; blank separator lines stay as "[mm:ss.xx] ").
- multi-timestamp lines are expanded; lines are sorted by timestamp.

Metadata files: singles -> metadata/<name>.json; album tracks ->
metadata/<album dir>/<track>.json. Existing values are never overwritten
(manual edits win), so the script is safe to re-run.

A tags.csv inside an album dir (columns: track,title,lyricist,composer,
compilation) is imported into the track metadata of that album.

Everything missing or suspicious is listed in metadata/_log.txt.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.common import safe_print
from lib.concat_auds import (
    AUDIO_EXTENSIONS,
    _detect_lrc_variant,
)

DEFAULT_GLOSSARY = Path(r"C:\Users\User\Share\files\tables\glossary_zh-cn.tsv")

MEDIA_DIR = Path("medias")
META_DIR = Path("metadata")
LOG_NAME = "_log.txt"

TAG_RE = re.compile(r"\[(\d{1,3}):(\d{1,2}(?:\.\d{1,3})?)\]")
META_TAG_RE = re.compile(r"^\[([A-Za-z][A-Za-z0-9#/_ -]*):(.*)\]$")
ISRC_RE = re.compile(r"^ISRC[\s\-:]*(.+)$", re.IGNORECASE)
COLON_RE = re.compile(r"^([^:：]{1,60}?)\s*[:：]\s*(.*?)\s*$")
TRAILING_SLASH_RE = re.compile(r"\s*//+\s*$")
ASCII_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 &.,'\-/()]*$")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
TRACK_NO_RE = re.compile(r"^(\d+)[.\s]")

# Credit lines without a colon, matched against the whole text.
NO_COLON_CREDITS = [
    (
        re.compile(r"^(?:strings? )?recorded at (.+?) by (.+)$", re.IGNORECASE),
        "recording",
        "{2} ({1})",
    ),
    (re.compile(r"^(.*recorded at.*)$", re.IGNORECASE), "recording", "{1}"),
    (re.compile(r"^mixed at (.+?) by (.+)$", re.IGNORECASE), "mixing", "{2} ({1})"),
    (re.compile(r"^(.*mixed at.*)$", re.IGNORECASE), "mixing", "{1}"),
    (re.compile(r"^recorded by (.+)$", re.IGNORECASE), "recording", "{1}"),
    (re.compile(r"^mixed by (.+)$", re.IGNORECASE), "mixing", "{1}"),
    (
        re.compile(r"^(?:cd )?mastered by (.+?) at (.+)$", re.IGNORECASE),
        "others_mastering",
        "{1} ({2})",
    ),
    (
        re.compile(r"^(?:cd )?mastered by (.+)$", re.IGNORECASE),
        "others_mastering",
        "{1}",
    ),
    (
        re.compile(r"^.*engineered.*? by (.+)$", re.IGNORECASE),
        "others_engineering",
        "{1}",
    ),
    (
        re.compile(r"^.*co-produced by (.+)$", re.IGNORECASE),
        "others_co_production",
        "{1}",
    ),
    (
        re.compile(r"^.*co-ordination by (.+)$", re.IGNORECASE),
        "others_co_ordination",
        "{1}",
    ),
    (
        re.compile(r"^strings arranged by (.+)$", re.IGNORECASE),
        "others_strings_arrangement",
        "{1}",
    ),
    (
        re.compile(r"^special thanks[ \-]+(.+)$", re.IGNORECASE),
        "others_special_thanks",
        "{1}",
    ),
    (re.compile(r"^produced by (.+)$", re.IGNORECASE), "director", "{1}"),
    (
        re.compile(r"^\(?P\)?\s*&\s*\(?C\)?\)?\s*(.+)$", re.IGNORECASE),
        "copyright",
        "{1}",
    ),
]

# Role vocabulary for generic "Guitars by X" credit lines.
ROLE_TOKENS = {
    "arranged",
    "arrangement",
    "bass",
    "cello",
    "cellos",
    "chorus",
    "dj",
    "drums",
    "flute",
    "guitar",
    "guitars",
    "harmonica",
    "horn",
    "horns",
    "keyboard",
    "keyboards",
    "percussion",
    "piano",
    "programmer",
    "programming",
    "rap",
    "scratch",
    "sax",
    "string",
    "strings",
    "synth",
    "synthesizer",
    "synthesizers",
    "trumpet",
    "viola",
    "violins",
    "violin",
    "vocal",
    "vocals",
}

GENERIC_BY_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 &,/']*?) by ([^ ].+)$")


def generic_by_credit(text: str) -> tuple[str, str] | None:
    """Handle "Strings by X" / "Programming & Guitars by Y" style lines."""
    m = GENERIC_BY_RE.match(text)
    if not m:
        return None
    roles, who = m.group(1), m.group(2).strip()
    tokens = [
        t.strip().lower().rstrip("s")
        for part in re.split(r"[/,&]", roles)
        for t in [part.strip()]
        if t.strip()
    ]
    hits = [t for t in tokens if t in ROLE_TOKENS]
    if not hits or not who:
        return None
    distinct = list(dict.fromkeys(hits))
    if len(distinct) == 1:
        key = EN_EXTRA.get(distinct[0]) or EN_EXTRA.get(distinct[0] + "s")
        if not key:
            key = f"others_{distinct[0]}"
        return key, who
    return "others_" + "_".join(distinct), who


# Expected credits checked for the manual-fill log.
CORE_KEYS = ("lyricist", "composer", "compilation")

# Chinese labels without a glossary entry -> English key (others_* by default).
ZH_EXTRA = {
    "过带录音师": "recording",
    "配唱录音师": "recording",
    "弦乐录音师": "recording",
    "混音录音师": "mixing",
    "弦乐录音室": "others_recording_studio",
    "录音室": "others_recording_studio",
    "混音室": "others_mixing_studio",
    "混音录音室": "others_mixing_studio",
    "过带": "recording",
    "弦乐编写": "others_strings_arrangement",
    "弦乐编写助理": "others_strings_arrangement",
    "弦乐助理": "others_strings",
    "合声": "others_backing_vocals",
    "和声": "others_backing_vocals",
    "合唱": "others_backing_vocals",
    "合声编写": "others_vocal_arrangement",
    "和声编写": "others_vocal_arrangement",
    "合声编写 & 合声": "others_vocal_arrangement",
    "采样": "others_sampling",
    "策划": "others_planning",
    "编程": "others_programming",
    "合成器": "others_synthesizer",
    "弦乐统筹": "others_strings_coordination",
    "吉他": "others_guitar",
    "电吉他": "others_electric_guitar",
    "吉他solo": "others_guitar_solo",
    "贝斯": "others_bass",
    "鼓": "others_drums",
    "钢琴": "others_piano",
    "小提琴": "others_violin",
    "中提琴": "others_viola",
    "大提琴": "others_cello",
    "小号": "others_trumpet",
    "弦乐": "others_strings",
    "弦乐团": "others_strings",
    "乐团": "others_ensemble",
    "四重奏": "others_quartet",
    "女声": "others_female_vocals",
    "韩文rap": "others_korean_rap",
}

# English labels without a glossary entry -> key.
EN_EXTRA = {
    "produced by": "director",
    "co-production": "others_co_production",
    "chorus by": "others_backing_vocals",
    "chorus": "others_backing_vocals",
    "guitar": "others_guitar",
    "guitars": "others_guitar",
    "guitar solo": "others_guitar_solo",
    "ending solo": "others_ending_solo",
    "bass": "others_bass",
    "c.bass": "others_bass",
    "bass & acoustic bass": "others_bass",
    "drums": "others_drums",
    "piano": "others_piano",
    "keyboards": "others_keyboards",
    "strings": "others_strings",
    "string arrangement": "others_strings_arrangement",
    "strings arrangement": "others_strings_arrangement",
    "1st violin": "others_violin",
    "2nd violin": "others_violin",
    "1st violins": "others_violin",
    "2nd violins": "others_violin",
    "violin": "others_violin",
    "violins": "others_violin",
    "viola": "others_viola",
    "violas": "others_viola",
    "violae": "others_viola",
    "cello": "others_cello",
    "celli": "others_violoncello",
    "cellos": "others_violoncello",
    "programmer": "others_programming",
    "programer": "others_programming",
    "programming": "others_programming",
    "all programming": "others_programming",
    "scratch": "others_scratch",
    "rap": "others_rap",
    "mandorin": "others_mandolin",
    "studios": "others_studios",
    "credit to": "others_credit_to",
    "isrc": "others_isrc",
    "op": "publisher",
    "os": "others_os",
    "sp": "publisher",
    "string scoring & arrangment": "others_strings_arrangement",
    "string scoring & arrangement": "others_strings_arrangement",
    "additional programming": "others_programming",
}

# Non-credit bracket tags in LRC headers.
META_TAG_DROP = {"ti", "title", "by", "re", "ve", "offset", "length", "au"}

# Lookup keys are whitespace-stripped, matching how labels are normalized.
ZH_EXTRA = {re.sub(r"\s+", "", k).lower(): v for k, v in ZH_EXTRA.items()}
EN_EXTRA = {re.sub(r"\s+", "", k).lower(): v for k, v in EN_EXTRA.items()}


def parse_glossary(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Build (music, other) zh-label -> english-key maps from the glossary TSV.

    The "Music tag" section wins over other sections (e.g. film credits also
    use 作曲人, where it means compositor, not composer).
    """
    music: dict[str, str] = {}
    other: dict[str, str] = {}
    if not path.is_file():
        safe_print(f"Error: glossary not found: {path}")
        sys.exit(1)
    for raw in path.read_text(encoding="utf-8").splitlines():
        if ":" not in raw or "\t" not in raw:
            continue
        head, _, zh = raw.partition("\t")
        domain, _, key = head.partition(":")
        key = key.strip().lower()
        if not key:
            continue
        target = music if domain.strip() == "Music tag" else other
        syns = {key.lower()} | {
            s.strip().lower() for s in re.split(r"[,，、]", zh) if s.strip()
        }
        for syn in syns:
            syn = re.sub(r"[()（）][^()（）]*[()（）]", "", syn).strip()
            if syn and syn not in target:
                target[syn] = key
    return music, other


def lookup_key(
    label: str, music: dict[str, str], other: dict[str, str]
) -> tuple[str, str] | None:
    """Map a credit label to (json_key, source). None = not a credit label."""
    norm = re.sub(r"\s+", "", label).lower()
    norm = re.sub(r"[()（）]", "", norm)
    # Exact glossary hits first, even single-char ones (词/曲).
    if norm in music:
        return music[norm], "glossary"
    if norm in other:
        return other[norm], "glossary"
    if norm in ZH_EXTRA:
        return ZH_EXTRA[norm], "extra"
    if norm in EN_EXTRA:
        return EN_EXTRA[norm], "extra"
    has_cjk = bool(CJK_RE.search(norm))
    if len(norm) < 2:
        return None
    # Prefix match in either direction, CJK only (编曲 ~ 编曲人, 混音助理 ~ 混音).
    # ASCII norms are too greedy here ("sp" would match "special effects teeth").
    if has_cjk:
        for syn, key in music.items():
            if len(syn) >= 2 and (norm.startswith(syn) or syn.startswith(norm)):
                return key, "glossary"
        for syn, key in other.items():
            if len(syn) >= 2 and (norm.startswith(syn) or syn.startswith(norm)):
                return key, "glossary"
        # Mixed label like "Beijing String Session Co-ordination 弦乐统筹":
        # retry with the CJK substring.
        cjk_run = "".join(CJK_RE.findall(norm))
        if cjk_run and cjk_run != norm:
            if cjk_run in ZH_EXTRA:
                return ZH_EXTRA[cjk_run], "extra"
            for syn, key in music.items():
                if len(syn) >= 2 and (
                    cjk_run.startswith(syn) or syn.startswith(cjk_run)
                ):
                    return key, "glossary"
            for syn, key in other.items():
                if len(syn) >= 2 and (
                    cjk_run.startswith(syn) or syn.startswith(cjk_run)
                ):
                    return key, "glossary"
    elif ASCII_LABEL_RE.match(label.strip()):
        ascii_key = re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_")
        return f"others_{ascii_key}", "others"
    return None


def format_lrc_ts(minutes: int, seconds: float) -> str:
    return f"[{minutes:02d}:{seconds % 60:05.2f}]"


def parse_timestamp(m: re.Match[str]) -> float:
    return int(m.group(1)) * 60 + float(m.group(2))


def clean_text(text: str) -> str:
    return TRAILING_SLASH_RE.sub("", text).strip()


def is_title_line(text: str, artist: str, line_no: int) -> bool:
    if line_no > 2 or " - " not in text or not artist:
        return False
    rest = text.rsplit(" - ", 1)[1]
    return artist in rest


def write_lrc(path: Path, content: str, dry_run: bool) -> None:
    """Write LRC without newline translation (keep the intended LF/CRLF)."""
    if dry_run:
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(content)


def process_lrc(
    path: Path, artist: str, music: dict[str, str], other: dict[str, str]
) -> tuple[str, list[tuple[str, str]], list[str], list[str]]:
    """Clean one LRC.

    Returns (new_content, credits, unknown_labels, conflicts).
    credits preserve file order; first value wins, later different values go to
    conflicts.
    """
    raw_bytes = path.read_bytes()
    text = raw_bytes.decode("utf-8-sig", errors="replace")
    eol = "\r\n" if text.count("\r\n") >= max(1, text.count("\n") // 2) else "\n"

    lyrics: list[tuple[float, int, str]] = []
    credits: list[tuple[str, str]] = []
    conflicts: list[str] = []
    unknown: list[str] = []
    seen: dict[str, str] = {}

    def add_credit(key: str, value: str, label: str, source: str) -> None:
        value = value.strip()
        if not value:
            return
        if key == "title":
            return  # title not needed
        if key in seen:
            if seen[key] != value:
                conflicts.append(
                    f'{key} "{seen[key]}" ≠ "{value}"（保留 "{seen[key]}"）'
                )
            return
        seen[key] = value
        credits.append((key, value))
        if source == "others":
            unknown.append(f'"{label}" → {key}')

    for line_no, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        if not s:
            continue
        meta_tag = META_TAG_RE.match(s)
        if meta_tag:
            label, value = meta_tag.group(1).strip(), meta_tag.group(2).strip()
            low = label.lower()
            if low in ("ar", "artist"):
                add_credit("artist", value, label, "extra")
            elif low not in META_TAG_DROP:
                key = f"others_{re.sub(r'[^a-z0-9]+', '_', low).strip('_')}"
                add_credit(key, value, label, "others")
            continue
        pos = 0
        tags: list[float] = []
        while True:
            m = TAG_RE.match(s, pos)
            if not m:
                break
            tags.append(parse_timestamp(m))
            pos = m.end()
        body = s[pos:]
        if not tags:
            continue  # non-timestamped line: dropped
        t = clean_text(body)
        if not t:
            for ts in tags:
                lyrics.append((ts, line_no, ""))
            continue
        if is_title_line(t, artist, line_no):
            continue
        isrc = ISRC_RE.match(t)
        if isrc:
            add_credit("others_isrc", isrc.group(1).strip(), "ISRC", "extra")
            continue
        cm = COLON_RE.match(t)
        if cm:
            label, value = cm.group(1).strip(), cm.group(2)
            if value.strip():
                hit = lookup_key(label, music, other)
                if hit:
                    add_credit(hit[0], value, label, hit[1])
                    continue
            elif lookup_key(label, music, other):
                continue  # empty credit line ("Strings:") carries no info: drop
        else:
            for pattern, key, fmt in NO_COLON_CREDITS:
                nm = pattern.match(t)
                if nm:
                    groups = nm.groups()
                    value = fmt
                    for idx, g in enumerate(groups, 1):
                        value = value.replace(f"{{{idx}}}", (g or "").strip())
                    add_credit(key, value.strip(), nm.group(0), "extra")
                    break
            else:
                gb = generic_by_credit(t)
                if gb:
                    add_credit(gb[0], gb[1], t, "extra")
                else:
                    for ts in tags:
                        lyrics.append((ts, line_no, t))
            continue
        for ts in tags:
            lyrics.append((ts, line_no, t))

    lyrics.sort(key=lambda item: (item[0], item[1]))
    lines = [
        f"{format_lrc_ts(int(ts) // 60, ts % 60)} {text}" for ts, _, text in lyrics
    ]
    return eol.join(lines), credits, unknown, conflicts


def load_meta_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        safe_print(f"Error: invalid JSON {path}: {e}")
        sys.exit(1)


def write_meta_json(path: Path, data: dict, dry_run: bool) -> bool:
    content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8") == content:
        return False
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return True


def merge_credits(
    existing: dict, credits: list[tuple[str, str]]
) -> tuple[dict, list[str]]:
    """existing wins; add credits for keys not already present."""
    merged = dict(existing)
    skipped = [f'{k} "{v}"' for k, v in credits if k in merged]
    for k, v in credits:
        if k not in merged:
            merged[k] = v
    return merged, skipped


def order_meta(data: dict) -> dict:
    def rank(k: str) -> tuple[int, str]:
        if k == "artist":
            return (0, k)
        if k in CORE_KEYS or k in ("director", "supervisor"):
            return (1, k)
        if not k.startswith("others_"):
            return (2, k)
        return (3, k)

    return dict(sorted(data.items(), key=lambda kv: rank(kv[0])))


def track_no(stem: str) -> str | None:
    m = TRACK_NO_RE.match(stem)
    return m.group(1) if m else None


def meta_path_for(album_dir: str | None, stem: str) -> Path:
    if album_dir:
        return META_DIR / album_dir / f"{stem}.json"
    return META_DIR / f"{stem}.json"


def import_tags_csv(
    album_dir: str, csv_path: Path, stems: list[str]
) -> dict[str, list[tuple[str, str]]]:
    """Read album tags.csv -> {track stem: [(key, value), ...]}."""
    result: dict[str, list[tuple[str, str]]] = {}
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            no = (row.get("track") or "").strip()
            stem = next((s for s in stems if track_no(s) == no and no), None)
            if not stem:
                continue
            pairs = [
                (k, (row.get(k) or "").strip())
                for k in ("lyricist", "composer", "compilation")
            ]
            result[stem] = [(k, v) for k, v in pairs if v]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Strip non-lyric lines from LRCs into metadata/ JSON files."
    )
    parser.add_argument("--dry-run", action="store_true", help="report only")
    parser.add_argument(
        "--glossary",
        type=Path,
        default=DEFAULT_GLOSSARY,
        help="zh/en glossary TSV with a 'Music tag' section",
    )
    args = parser.parse_args()
    music, other = parse_glossary(args.glossary)

    if not MEDIA_DIR.is_dir():
        safe_print(f"Error: {MEDIA_DIR}/ not found (run from a category dir)")
        return 1

    log_empty_lyrics: list[str] = []
    log_missing_meta: list[str] = []
    log_mp3_no_lrc: list[str] = []
    log_conflicts: list[str] = []
    log_unknown: list[str] = []
    n_lrc_rewritten = n_meta_written = 0

    singles = sorted(MEDIA_DIR.glob("*.lrc"))
    albums = sorted(p for p in MEDIA_DIR.iterdir() if p.is_dir())

    def process_track(album_dir: str | None, lrc: Path, artist: str) -> None:
        nonlocal n_lrc_rewritten, n_meta_written
        new_content, credits, unknown, conflicts = process_lrc(
            lrc, artist, music, other
        )
        if artist:
            credits.insert(0, ("artist", artist))
        rel = lrc.relative_to(MEDIA_DIR.parent)

        old_text = lrc.read_bytes().decode("utf-8-sig", errors="replace")
        if new_content != old_text:
            n_lrc_rewritten += 1
            write_lrc(lrc, new_content, args.dry_run)
            safe_print(f"{'[dry] ' if args.dry_run else ''}lrc cleaned: {rel}")

        if not new_content.strip():
            log_empty_lyrics.append(str(rel))

        mpath = meta_path_for(album_dir, lrc.stem)
        existing = load_meta_json(mpath)
        merged, _ = merge_credits(existing, credits)
        merged = order_meta(merged)
        if (merged != existing or not mpath.exists()) and write_meta_json(
            mpath, merged, args.dry_run
        ):
            n_meta_written += 1
            safe_print(f"{'[dry] ' if args.dry_run else ''}metadata: {mpath}")

        missing = [k for k in CORE_KEYS if k not in merged]
        if missing:
            log_missing_meta.append(f"{mpath}: 缺 {'、'.join(missing)}")
        for c in conflicts:
            log_conflicts.append(f"{mpath}: {c}")
        for u in unknown:
            log_unknown.append(f"{rel}: {u}")

    # Singles (top-level lrc files).
    for lrc in singles:
        artist = lrc.stem.split(" - ", 1)[0] if " - " in lrc.stem else ""
        process_track(None, lrc, artist)

    # Albums (one dir per album, tracks numbered "NN. title").
    for album in albums:
        artist = album.name.split(" - ", 1)[0] if " - " in album.name else ""
        all_lrc = sorted(album.glob("*.lrc"))
        stems = {p.stem for p in all_lrc}
        csv_credits: dict[str, list[tuple[str, str]]] = {}
        csv_path = album / "tags.csv"
        if csv_path.is_file():
            csv_credits = import_tags_csv(album.name, csv_path, sorted(stems))

        for lrc in all_lrc:
            variant = _detect_lrc_variant(lrc.stem, stems)
            if variant:
                # language variant: clean the file, but metadata belongs to the
                # base track and was already processed.
                new_content, _, _, _ = process_lrc(lrc, artist, music, other)
                old_text = lrc.read_bytes().decode("utf-8-sig", errors="replace")
                if new_content != old_text:
                    n_lrc_rewritten += 1
                    write_lrc(lrc, new_content, args.dry_run)
                    safe_print(
                        f"{'[dry] ' if args.dry_run else ''}lrc cleaned: "
                        f"{lrc.relative_to(MEDIA_DIR.parent)}"
                    )
                continue
            process_track(album.name, lrc, artist)
            if lrc.stem in csv_credits:
                mpath = meta_path_for(album.name, lrc.stem)
                existing = load_meta_json(mpath)
                merged, _ = merge_credits(existing, csv_credits[lrc.stem])
                merged = order_meta(merged)
                if merged != existing and write_meta_json(mpath, merged, args.dry_run):
                    n_meta_written += 1
                    safe_print(
                        f"{'[dry] ' if args.dry_run else ''}metadata(+csv): {mpath}"
                    )

        # audio files without any matching lrc
        audio_files = sorted(
            f
            for f in album.iterdir()
            if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
        )
        for audio in audio_files:
            no = track_no(audio.stem)
            if not any(track_no(s) == no and no for s in stems):
                log_mp3_no_lrc.append(str(audio.relative_to(MEDIA_DIR.parent)))

    # top-level audio files without lrc
    lrc_stems = {p.stem for p in singles}
    for audio in sorted(MEDIA_DIR.iterdir()):
        if (
            audio.is_file()
            and audio.suffix.lower() in AUDIO_EXTENSIONS
            and audio.stem not in lrc_stems
        ):
            log_mp3_no_lrc.append(str(audio.relative_to(MEDIA_DIR.parent)))

    sections = [
        ("清理后无歌词（需人工补歌词）", log_empty_lyrics),
        (
            "缺失 meta（占位 json 已创建，缺: lyricist/composer/compilation）",
            log_missing_meta,
        ),
        ("mp3 无对应 lrc", log_mp3_no_lrc),
        ("credit 冲突（保留首次出现的值）", log_conflicts),
        ("未识别标签（已归入 others_*，请检查）", log_unknown),
    ]
    stamp = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    out = [
        f"# prep_lrc_meta.py 日志（{stamp} 生成，重跑脚本会覆盖本文件）",
        f"# lrc 重写 {n_lrc_rewritten} 个，metadata 写入 {n_meta_written} 个"
        + ("（dry-run，未实际写入）" if args.dry_run else ""),
        "",
    ]
    for title, items in sections:
        if not items:
            continue
        out.append(f"## {title}")
        out.extend(f"- {i}" for i in items)
        out.append("")
    log_path = META_DIR / LOG_NAME
    if not args.dry_run:
        META_DIR.mkdir(exist_ok=True)
        log_path.write_text("\n".join(out), encoding="utf-8")
    safe_print(
        f"\n{'[dry-run] ' if args.dry_run else ''}done: lrc×{n_lrc_rewritten}, "
        f"meta×{n_meta_written}, log → {log_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
