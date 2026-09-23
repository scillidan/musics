"""MIDI sheet-music cover video generator."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.common import (
    PROJECT_ROOT,
    compile_typ,
    load_meta,
    make_mp4,
    merge_meta,
    run_checked,
    safe_print,
    strip_ext,
    typ_str,
    write_typ_if_changed,
)

SUBDIR = "mid"
MIDI_DIR = "mids"
META_DIR = Path("metadata")
OUTPUT_BASE = "_output"
SCORE_PDF_DIR = Path(OUTPUT_BASE, "score_pdfs")
SCORE_PAGE_DIR = Path(OUTPUT_BASE, "score_pages")
MP3_DIR = Path(OUTPUT_BASE, "mp3s")

MUSESCORE_EXE = Path(
    shutil.which("musescore")
    or shutil.which("MuseScore")
    or "E:/Scoop/apps/musescore/current/bin/MuseScore.exe"
)
PDFTOPPM_EXE = shutil.which("pdftoppm") or "pdftoppm"
MUSESCORE_STYLE = SCRIPT_DIR / "mid_no_page_numbers.mss"

AUDIO_EXTENSIONS = (".mp3", ".wav", ".flac", ".m4a", ".ogg", ".opus")


def find_midi(name: str) -> Path | None:
    path = Path(MIDI_DIR) / f"{name}.mid"
    if path.exists():
        return path
    path = Path(MIDI_DIR) / f"{name}.midi"
    if path.exists():
        return path
    return None


def find_media(name: str) -> Path | None:
    for ext in AUDIO_EXTENSIONS:
        path = Path(MIDI_DIR) / f"{name}{ext}"
        if path.exists():
            return path
        path = Path("medias") / f"{name}{ext}"
        if path.exists():
            return path
    return None


def render_score_pdf(midi_path: Path, score_pdf: Path) -> bool:
    score_pdf.parent.mkdir(parents=True, exist_ok=True)
    safe_print(f"Rendering score PDF: {score_pdf.name}")
    env = dict(os.environ)
    env["LANG"] = "C"
    env["LC_ALL"] = "C"
    cmd = [
        str(MUSESCORE_EXE),
        "-o",
        str(score_pdf),
    ]
    if MUSESCORE_STYLE.exists():
        cmd.extend(["-S", str(MUSESCORE_STYLE)])
    cmd.append(str(midi_path))
    return subprocess.run(cmd, check=False, env=env).returncode == 0


def split_score_pdf(score_pdf: Path, prefix: str) -> list[Path]:
    SCORE_PAGE_DIR.mkdir(parents=True, exist_ok=True)
    safe_print(f"Splitting score pages: {prefix}")
    env = dict(os.environ)
    env["LANG"] = "C"
    env["LC_ALL"] = "C"
    subprocess.run(
        [
            PDFTOPPM_EXE,
            "-png",
            "-r",
            "300",
            str(score_pdf),
            str(SCORE_PAGE_DIR / prefix),
        ],
        check=False,
        env=env,
    )
    pages = sorted(SCORE_PAGE_DIR.glob(f"{prefix}-*.png"))
    return pages


def generate_typ(name: str, page_paths: list[str], meta: dict) -> str:
    page_args = ", ".join(f'"{typ_str(p)}"' for p in page_paths)
    trailing = "," if len(page_paths) == 1 else ""
    page_array = f"({page_args}{trailing})"

    params = [
        f'  title: "{typ_str(name)}"',
        f"  pages: {page_array}",
    ]

    for key in (
        "page-size",
        "flipped",
        "page-width",
        "page-height",
        "gutter",
        "title-size",
        "page-number-size",
        "title-offset",
        "page-number-offset",
    ):
        if key in meta:
            params.append(f"  {key}: {meta[key]}")

    return (
        '#import "/scripts/templates/mid.typ": mid-cover\n\n'
        "#mid-cover(\n" + ",\n".join(params) + "\n)\n"
    )


def paths_for(name: str) -> dict:
    return {
        "typ": Path(OUTPUT_BASE, "typs", f"{name}.typ"),
        "pdf": Path(OUTPUT_BASE, "pdfs", f"{name}.pdf"),
        "jpg": Path(OUTPUT_BASE, "jpgs", f"{name}.jpg"),
        "mp4": Path(OUTPUT_BASE, f"{name}.mp4"),
        "score_pdf": SCORE_PDF_DIR / f"{name}_score.pdf",
        "mp3": MP3_DIR / f"{name}.mp3",
    }


def ensure_mid_output_dirs() -> None:
    Path(OUTPUT_BASE).mkdir(exist_ok=True)
    Path(OUTPUT_BASE, "typs").mkdir(exist_ok=True)
    Path(OUTPUT_BASE, "pdfs").mkdir(exist_ok=True)
    Path(OUTPUT_BASE, "jpgs").mkdir(exist_ok=True)
    SCORE_PDF_DIR.mkdir(parents=True, exist_ok=True)
    SCORE_PAGE_DIR.mkdir(parents=True, exist_ok=True)
    MP3_DIR.mkdir(parents=True, exist_ok=True)


def project_path(local: Path) -> Path:
    return PROJECT_ROOT / SUBDIR / local


def generate_typ_file(name: str) -> int:
    ensure_mid_output_dirs()
    paths = paths_for(name)

    midi_path = find_midi(name)
    if not midi_path:
        safe_print(f"Error: MIDI not found for {name} in {MIDI_DIR}/")
        return 1

    defaults, item_meta = load_meta(name, META_DIR)
    meta = merge_meta(defaults, item_meta)

    if not render_score_pdf(midi_path, paths["score_pdf"]):
        safe_print(f"Error: failed to render score PDF for {name}")
        return 1

    pages = split_score_pdf(paths["score_pdf"], name)
    if not pages:
        safe_print(f"Error: no score pages generated for {name}")
        return 1

    page_paths = [f"/{SUBDIR}/{p.as_posix()}" for p in pages[:2]]

    typ_content = generate_typ(name, page_paths, meta)
    if write_typ_if_changed(paths["typ"], typ_content):
        safe_print(f"Generated: {paths['typ']}")
    else:
        safe_print(f"Reusing existing typ: {paths['typ']}")

    return 0


def compile_one(name: str) -> int:
    paths = paths_for(name)
    project_typ = project_path(paths["typ"])
    project_pdf = project_path(paths["pdf"])
    project_png = project_pdf.with_suffix(".png")

    if not compile_typ(project_typ, project_pdf):
        return 1

    # Typst can produce PNG directly; avoid ImageMagick PDF delegate issues.
    safe_print(f"Converting to PNG: {project_png.name}")
    if not run_checked(
        [
            "typst",
            "compile",
            "--root",
            ".",
            str(project_typ),
            str(project_png),
            "-f",
            "png",
        ],
        cwd=PROJECT_ROOT,
    ):
        return 1

    safe_print(f"Converting to JPG: {paths['jpg'].name}")
    if not run_checked(
        [
            "magick",
            str(project_png),
            "-resize",
            "1528x1080!",
            "-background",
            "white",
            "-alpha",
            "remove",
            "-quality",
            "90",
            str(paths["jpg"]),
        ]
    ):
        return 1

    safe_print(f"Draft ready: {paths['jpg']}")
    return 0


def typ_one(name: str) -> int:
    if generate_typ_file(name) != 0:
        return 1
    return compile_one(name)


def render_mp3(midi_path: Path, mp3_path: Path) -> bool:
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    safe_print(f"Rendering MP3 from MIDI: {mp3_path.name}")
    env = dict(os.environ)
    env["LANG"] = "C"
    env["LC_ALL"] = "C"
    return (
        subprocess.run(
            [str(MUSESCORE_EXE), "-o", str(mp3_path), str(midi_path)],
            check=False,
            env=env,
        ).returncode
        == 0
    )


def resolve_audio(name: str, midi_path: Path) -> Path | None:
    media = find_media(name)
    if media:
        return media

    paths = paths_for(name)
    mp3_path = paths["mp3"]
    if mp3_path.exists():
        return mp3_path

    if render_mp3(midi_path, mp3_path):
        return mp3_path

    return None


def add_one(name: str) -> int:
    paths = paths_for(name)

    if paths["typ"].exists():
        safe_print(f"Reusing existing typ: {paths['typ']}")
        if compile_one(name) != 0:
            return 1
    else:
        if typ_one(name) != 0:
            return 1

    midi_path = find_midi(name)
    if not midi_path:
        safe_print(f"Error: MIDI not found for {name}")
        return 1

    audio_path = resolve_audio(name, midi_path)
    if not audio_path:
        safe_print(f"Error: audio not found and MIDI render failed for {name}")
        return 1

    if not make_mp4(paths["jpg"], audio_path, paths["mp4"]):
        return 1
    safe_print(f"MP4 ready: {paths['mp4']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="MIDI sheet-music video generator")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser(
        "typ", help="generate cover only (typ/pdf/jpg), no audio"
    ).add_argument("name")

    sub.add_parser(
        "add", help="generate mp4 (reuse typ if present, else create from scratch)"
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
