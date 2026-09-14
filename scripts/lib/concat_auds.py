"""Generate chapters, concat audio, and merge LRC files for albums."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__" and __package__ is None:
    # Allow running this file directly as a script.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.lrc_utils import (
    format_timestamp_lrc,
    format_timestamp_srt,
    parse_lrc,
)

AUDIO_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".flac",
    ".aac",
    ".m4a",
    ".m4b",
    ".ogg",
    ".opus",
    ".wma",
}


def get_duration(file_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return float(result.stdout.strip())


def format_time_chapters(seconds: float) -> str:
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def generate_chapters(
    audio_files: list[Path], output_path: Path
) -> list[tuple[str, str]]:
    accumulated = 0.0
    chapters: list[tuple[str, str]] = []
    for audio_file in audio_files:
        ts = format_time_chapters(accumulated)
        title = (
            audio_file.stem.split(".", 1)[-1].strip()
            if "." in audio_file.stem
            else audio_file.stem
        )
        chapters.append((ts, title))
        accumulated += get_duration(audio_file)
        print(f"OK: {audio_file.name}")

    output_path.write_text(
        "\n".join(
            f"{ts} {idx:02d}. {title}" for idx, (ts, title) in enumerate(chapters, 1)
        ),
        encoding="utf-8",
    )
    print(f"\nChapters saved to: {output_path}")
    return chapters


def merge_lrc_to_srt(
    lrc_files: list[Path], audio_files: list[Path], srt_path: Path
) -> None:
    all_subs: list[tuple[float, float, str]] = []
    accumulated = 0.0
    for lrc_file, audio_file in zip(lrc_files, audio_files):
        track_duration = get_duration(audio_file)
        lines = parse_lrc(lrc_file)
        for i, (start_ts, text) in enumerate(lines):
            adjusted_start = accumulated + start_ts
            adjusted_end = (
                accumulated + lines[i + 1][0]
                if i + 1 < len(lines)
                else min(adjusted_start + 3.0, accumulated + track_duration)
            )
            all_subs.append((adjusted_start, adjusted_end, text))
        accumulated += track_duration

    srt_path.write_text(
        "\n\n".join(
            f"{idx}\n{format_timestamp_srt(start)} --> {format_timestamp_srt(end)}\n{text}"
            for idx, (start, end, text) in enumerate(all_subs, 1)
        ),
        encoding="utf-8",
    )


def merge_lang_lrc(
    lrc_files: list[Path], audio_files: list[Path], output_path: Path
) -> None:
    merged: list[tuple[float, str]] = []
    accumulated = 0.0
    for lrc_file, audio_file in zip(lrc_files, audio_files):
        for ts, text in parse_lrc(lrc_file):
            merged.append((accumulated + ts, text))
        accumulated += get_duration(audio_file)

    output_path.write_text(
        "\n".join(f"{format_timestamp_lrc(start)}{text}" for start, text in merged),
        encoding="utf-8",
    )


def concat_audio(audio_files: list[Path], output_path: Path) -> None:
    temp_dir = output_path.parent / "_temp"
    temp_dir.mkdir(exist_ok=True)
    try:
        temp_files: list[Path] = []
        for i, audio_file in enumerate(audio_files, 1):
            temp_path = temp_dir / f"{i:02d}{audio_file.suffix}"
            shutil.copy2(audio_file, temp_path)
            temp_files.append(temp_path)

        list_file = temp_dir / "_concat_list.txt"
        list_file.write_text(
            "\n".join(f"file '{tf.resolve()}'" for tf in temp_files),
            encoding="utf-8",
        )

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-codec:a",
                "libmp3lame",
                "-qscale:a",
                "1",
                str(output_path),
            ],
            check=True,
        )
        print(f"Concat saved to: {output_path}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _detect_lrc_variant(stem: str, known_stems: set[str]) -> str | None:
    """Return the normalized variant suffix if stem is <base>.<suffix> or <base>_<suffix>.

    Only treats it as a variant when the shorter base stem exists as another
    LRC file. This avoids hard-coding language names.
    """
    for sep in (".", "_"):
        if sep in stem:
            base_stem, suffix = stem.rsplit(sep, 1)
            # Suffix should be reasonably short; base must exist as an LRC.
            if suffix and len(suffix) <= 24 and base_stem in known_stems:
                return f".{suffix}"
    return None


def collect_files(
    input_dir: Path,
) -> tuple[list[Path], list[Path], dict[str, list[Path]]]:
    audio_files = sorted(
        f
        for f in input_dir.iterdir()
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
    )

    all_lrc = sorted(
        f for f in input_dir.iterdir() if f.is_file() and f.suffix.lower() == ".lrc"
    )
    lrc_stems = {f.stem for f in all_lrc}

    lrc_files: list[Path] = []
    lang_lrc_files: dict[str, list[Path]] = {}

    for f in all_lrc:
        variant = _detect_lrc_variant(f.stem, lrc_stems)
        if variant:
            lang_lrc_files.setdefault(variant, []).append(f)
        else:
            lrc_files.append(f)

    for files in lang_lrc_files.values():
        files.sort()

    return audio_files, lrc_files, lang_lrc_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Concat album audio and merge lyrics")
    parser.add_argument(
        "input_dir", type=Path, help="directory containing audio/lrc files"
    )
    parser.add_argument("--chapters", action="store_true", help="generate chapter file")
    parser.add_argument(
        "--concat", action="store_true", help="concat audio to <dirname>.mp3"
    )
    parser.add_argument("--lyrics", action="store_true", help="merge lyrics to srt/lrc")
    args = parser.parse_args()

    if not args.input_dir.is_dir():
        print(f"Error: not a directory: {args.input_dir}", file=sys.stderr)
        return 1

    audio_files, lrc_files, lang_lrc_files = collect_files(args.input_dir)
    if not audio_files:
        print("Error: no audio files found", file=sys.stderr)
        return 1

    base_name = args.input_dir.name
    cwd = Path.cwd()

    if args.chapters:
        generate_chapters(audio_files, cwd / f"{base_name}.mp3.chp")

    if args.concat:
        concat_audio(audio_files, cwd / f"{base_name}.mp3")

    if args.lyrics:
        all_groups: dict[str, list[Path]] = {"": lrc_files}
        all_groups.update(lang_lrc_files)
        for lang, files in all_groups.items():
            if not files:
                continue
            out_stem = f"{base_name}{lang}" if lang else base_name
            merge_lrc_to_srt(files, audio_files, cwd / f"{out_stem}.srt")
            merge_lang_lrc(files, audio_files, cwd / f"{out_stem}.lrc")

    if not any([args.chapters, args.concat, args.lyrics]):
        print(
            "Error: specify at least one of --chapters, --concat, --lyrics",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
