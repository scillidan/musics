"""Instrumental cover-only video generator."""

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
    make_mp4,
    pdf_to_jpg,
    safe_print,
    strip_ext,
    typ_str,
    write_typ_if_changed,
)

SUBDIR = "instrumental"


def find_media(name: str, medias_dir: str = "medias") -> Path | None:
    for ext in ("mp3", "wav", "flac", "m4a", "ogg", "opus"):
        path = Path(medias_dir) / f"{name}.{ext}"
        if path.exists():
            return path
    return None


def find_instrumental_cover(name: str, assets_dir: str = "assets") -> str | None:
    prefix = f"/{SUBDIR}/"
    for ext in ("jpg", "jpeg", "png"):
        path = Path(assets_dir) / f"{name}.{ext}"
        if path.exists():
            return f"{prefix}{assets_dir}/{path.name}"
    return None


def generate_typ(name: str, cover: str | None) -> str:
    cover_arg = f'"{typ_str(cover)}"' if cover else "none"
    return (
        '#import "/scripts/templates/instrumental.typ": instrumental-poster\n\n'
        "#instrumental-poster(\n"
        f'  name: "{typ_str(name)}",\n'
        f"  images: ({cover_arg},)\n"
        ")\n"
    )


def project_path(local: Path) -> Path:
    return PROJECT_ROOT / SUBDIR / local


def paths_for(name: str) -> dict:
    return {
        "typ": Path("_output/typs", f"{name}.typ"),
        "pdf": Path("_output/pdfs", f"{name}.pdf"),
        "jpg": Path("_output/jpgs", f"{name}.jpg"),
        "mp4": Path("_output", f"{name}.mp4"),
    }


def generate_typ_file(name: str) -> int:
    ensure_output_dirs()
    paths = paths_for(name)
    cover = find_instrumental_cover(name)
    if not cover:
        safe_print(f"Error: cover not found for {name}")
        return 1

    typ_content = generate_typ(name, cover)
    if write_typ_if_changed(paths["typ"], typ_content):
        safe_print(f"Generated: {paths['typ']}")
    else:
        safe_print(f"Reusing existing typ: {paths['typ']}")
    return 0


def compile_one(name: str) -> int:
    paths = paths_for(name)
    if not compile_typ(project_path(paths["typ"]), project_path(paths["pdf"])):
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
    if not make_mp4(paths["jpg"], media, paths["mp4"]):
        return 1
    safe_print(f"MP4 ready: {paths['mp4']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Instrumental cover video generator")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("typ", help="generate typ and compile pdf/jpg").add_argument("name")
    sub.add_parser(
        "add", help="compile pdf/jpg/mp4 (reuse _output/typs/*.typ if present)"
    ).add_argument("name")

    args = parser.parse_args()
    name = strip_ext(args.name)

    if args.cmd == "typ":
        return typ_one(name)
    if args.cmd == "add":
        return add_one(name)
    return 1


if __name__ == "__main__":
    sys.exit(main())
