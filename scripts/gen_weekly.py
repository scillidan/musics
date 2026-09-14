"""Weekly lyric video generator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.common import (
    PROJECT_ROOT,
    compile_typ,
    ensure_output_dirs,
    find_artist_images,
    find_cover,
    make_mp4,
    parse_artist_names_from_song_name,
    pdf_to_jpg,
    safe_print,
    strip_ext,
    typ_str,
    write_typ_if_changed,
)
from lib.lrc_to_srt import lrc_to_srt

SUBDIR = "weekly"


def find_media(name: str, medias_dir: str = "medias") -> Path | None:
    for ext in ("mp3", "wav", "flac", "m4a", "ogg", "opus"):
        path = Path(medias_dir) / f"{name}.{ext}"
        if path.exists():
            return path
    return None


def find_lrc(name: str, medias_dir: str = "medias") -> Path | None:
    path = Path(medias_dir) / f"{name}.lrc"
    return path if path.exists() else None


def generate_typ(
    name: str,
    cover: str | None,
    artists: list[str],
    lrc: Path | None,
) -> str:
    cover_arg = f'"{typ_str(cover)}"' if cover else "none"
    lrc_arg = f'"/{SUBDIR}/medias/{typ_str(name)}.lrc"' if lrc else "none"

    if artists:
        items = ", ".join(f'"{typ_str(a)}"' for a in artists)
        trailing = "," if len(artists) == 1 else ""
        artists_arg = f"({items}{trailing})"
    else:
        artists_arg = "()"

    param_lines = [
        f'  name: "{typ_str(name)}"',
        f"  cover: {cover_arg}",
        f"  artists: {artists_arg}",
        f"  lrc: {lrc_arg}",
        "  left-ratio: 0.35",
        "  spacing_all: 10pt",
        "  lyrics-columns: 1",
        "  lyrics-size: 0.55em",
    ]
    if len(artists) > 1:
        param_lines.extend(
            [
                "  // artist-grid-cols: 3",
                "  // artist-grid-rows: 1",
            ]
        )

    return (
        '#import "/scripts/templates/weekly.typ": lyric-poster\n\n'
        "#lyric-poster(\n" + ",\n".join(param_lines) + "\n)\n"
    )


def paths_for(name: str, output_base: str = "_output") -> dict:
    return {
        "typ": Path(output_base, "typs", f"{name}.typ"),
        "pdf": Path(output_base, "pdfs", f"{name}.pdf"),
        "jpg": Path(output_base, "jpgs", f"{name}.jpg"),
        "mp4": Path(output_base, f"{name}.mp4"),
    }


def generate_typ_file(name: str) -> int:
    ensure_output_dirs()
    paths = paths_for(name)
    cover = find_cover(name, subdir=SUBDIR)
    lrc = find_lrc(name)

    if not lrc:
        safe_print(f"Warning: lrc not found for {name}")

    artist_names = parse_artist_names_from_song_name(name)
    artists = find_artist_images(name, artist_names, subdir=SUBDIR)

    typ_content = generate_typ(name, cover, artists, lrc)
    if write_typ_if_changed(paths["typ"], typ_content):
        safe_print(f"Generated: {paths['typ']}")
    else:
        safe_print(f"Reusing existing typ: {paths['typ']}")
    return 0


def compile_one(name: str) -> int:
    paths = paths_for(name)
    project_typ = PROJECT_ROOT / SUBDIR / paths["typ"]
    project_pdf = PROJECT_ROOT / SUBDIR / paths["pdf"]
    if not compile_typ(project_typ, project_pdf):
        return 1
    if not pdf_to_jpg(paths["pdf"], paths["jpg"]):
        return 1
    safe_print(f"Draft ready: {paths['jpg']}")
    return 0


def typ_one(name: str) -> int:
    paths = paths_for(name)
    if paths["typ"].exists():
        safe_print(f"Reusing existing typ: {paths['typ']}")
        return compile_one(name)
    if generate_typ_file(name) != 0:
        return 1
    return compile_one(name)


def add_one(name: str) -> int:
    if typ_one(name) != 0:
        return 1

    paths = paths_for(name)
    media = find_media(name)
    if not media:
        safe_print(f"Error: media not found for {name}")
        return 1

    lrc = find_lrc(name)
    if lrc:
        srt_path = Path("_output", "srts", f"{name}.srt")
        lrc_to_srt(lrc, srt_path)
        safe_print(f"SRT ready: {srt_path}")

    if not make_mp4(paths["jpg"], media, paths["mp4"]):
        return 1
    safe_print(f"MP4 ready: {paths['mp4']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Weekly lyric video generator")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_typ = sub.add_parser("typ", help="generate typ and compile pdf/jpg")
    p_typ.add_argument("name", help="song name (without extension)")

    p_add = sub.add_parser(
        "add", help="compile pdf/jpg/mp4 (reuse _output/typs/*.typ if present)"
    )
    p_add.add_argument("name", help="song name (without extension)")

    args = parser.parse_args()
    name = strip_ext(args.name)

    if args.cmd == "typ":
        return typ_one(name)
    if args.cmd == "add":
        return add_one(name)

    return 1


if __name__ == "__main__":
    sys.exit(main())
