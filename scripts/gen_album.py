"""Album (song/ost) video generator."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.common import (
    PROJECT_ROOT,
    compile_typ,
    ensure_meta_file,
    ensure_output_dirs,
    find_artist_images,
    find_cover,
    load_meta,
    make_mp4,
    make_mp4_slides,
    merge_meta,
    pdf_to_jpg,
    safe_print,
    strip_ext,
    typ_str,
    write_typ_if_changed,
)
from lib.concat_auds import (
    AUDIO_EXTENSIONS,
    collect_files,
    concat_audio,
    generate_chapters,
    get_duration,
    merge_lang_lrc,
    merge_lrc_to_srt,
)

META_DIR = Path("metadata")
OUTPUT_BASE = "_output"
MP3_DIR = Path(OUTPUT_BASE, "mp3s")

# Values written to metadata/<album>.json when an album has no metadata file yet.
# Keyed by subdir because song and ost share this script.
NEW_META_DEFAULTS = {
    "ost": {"body-size": "1.1em"},
}


def find_album_cover(name: str, subdir: str = "") -> str | None:
    """Legacy cover lookup: assets/<name>.<ext> (ost convention)."""
    prefix = f"/{subdir}/" if subdir else "/"
    for ext in ("jpg", "jpeg", "png"):
        path = Path("assets") / f"{name}.{ext}"
        if path.exists():
            return f"{prefix}assets/{path.name}"
    return None


def find_album_input(name: str) -> tuple[str, Path, bool]:
    medias = Path("medias")
    candidate = medias / name
    if candidate.is_dir():
        return name, candidate, True

    for ext in AUDIO_EXTENSIONS:
        file_candidate = medias / f"{name}{ext}"
        if file_candidate.exists():
            return name, file_candidate, False

    safe_print(f"Error: no audio found for {name} in medias/")
    sys.exit(1)


def resolve_title_artist(name: str, meta: dict) -> tuple[str, str]:
    if "title" in meta:
        return meta["title"], meta.get("artist", "")

    split = meta.get("split-artist-title", True)
    if split and " - " in name:
        artist, title = name.split(" - ", 1)
        return title, artist

    return name, ""


QUOTED_STRING_KEYS = {
    "title",
    "artist",
    "year",
    "page-size",
    "chapters-path",
    "cover",
    "lrc",
}


def typ_value(key: str, value: Any) -> str:
    if value is None:
        return "none"
    if key == "images":
        if not value:
            return "()"
        items = ", ".join(f'"{typ_str(img)}"' for img in value)
        trailing = "," if len(value) == 1 else ""
        return f"({items}{trailing})"
    if key == "font":
        if not value:
            return "()"
        items = ", ".join(f'"{typ_str(f)}"' for f in value)
        return f"({items})"
    if key == "artists":
        if not value:
            return "()"
        items = ", ".join(f'"{typ_str(a)}"' for a in value)
        trailing = "," if len(value) == 1 else ""
        return f"({items}{trailing})"
    if key in QUOTED_STRING_KEYS:
        return f'"{typ_str(value)}"'
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (list, tuple)):
        items = ", ".join(typ_value("", item) for item in value)
        return f"({items})"
    if isinstance(value, dict):
        items = ", ".join(f"{k}: {typ_value('', v)}" for k, v in value.items())
        return f"({items})"
    return str(value)


def generate_typ(
    title: str,
    artist: str,
    year: str,
    images: list[str],
    cover: str | None,
    artists: list[str],
    chapters_path: str | None,
    lrc: str | None,
    meta: dict,
) -> str:
    params: list[tuple[str, str]] = [
        ("title", typ_value("title", title)),
        ("artist", typ_value("artist", artist)),
        ("year", typ_value("year", year)),
    ]

    if images:
        params.append(("images", typ_value("images", images)))
    params.append(("cover", typ_value("cover", cover)))
    params.append(("artists", typ_value("artists", artists)))
    params.append(("lrc", typ_value("lrc", lrc)))

    params.append(("chapters-path", typ_value("chapters-path", chapters_path)))

    for key in (
        "columns",
        "column-gutter",
        "left-ratio",
        "spacing-all",
        "page-size",
        "flipped",
        "font",
        "base-size",
        "title-size",
        "subtitle-size",
        "body-size",
        "lyrics-columns",
        "lyrics-size",
        "lyrics-spacing",
        "lyrics-paragraph-spacing",
        "lyrics-hanging-indent",
        "image-gutter",
    ):
        if key in meta:
            params.append((key, typ_value(key, meta[key])))

    param_lines = ",\n".join(f"  {k}: {v}" for k, v in params)

    return (
        '#import "/scripts/templates/album.typ": album-poster\n\n'
        f"#album-poster(\n{param_lines}\n)\n"
    )


def output_paths_for(name: str) -> dict:
    return {
        "typ": Path(OUTPUT_BASE, "typs", f"{name}.typ"),
        "pdf": Path(OUTPUT_BASE, "pdfs", f"{name}.pdf"),
        "jpg": Path(OUTPUT_BASE, "jpgs", f"{name}.jpg"),
        "mp4": Path(OUTPUT_BASE, f"{name}.mp4"),
    }


def audio_paths_for(name: str) -> dict:
    return {
        "mp3": MP3_DIR / f"{name}.mp3",
        "chp": Path(OUTPUT_BASE, f"{name}.mp4.chp"),
        "lrc": Path(OUTPUT_BASE, f"{name}.lrc"),
        "srt": Path(OUTPUT_BASE, "srts", f"{name}.srt"),
    }


def ensure_audio_output_dirs() -> None:
    Path(OUTPUT_BASE).mkdir(exist_ok=True)
    MP3_DIR.mkdir(exist_ok=True)
    Path(OUTPUT_BASE, "srts").mkdir(exist_ok=True)


def album_artist_names(album_name: str) -> list[str]:
    """Artist names from '<artist> - <album>' dirs/singles (artist first)."""
    if " - " not in album_name:
        return []
    return [album_name.split(" - ", 1)[0].strip()]


def load_album_context(
    name: str,
) -> tuple[str, Path, bool, dict, str, str, str, list[str], str | None, list[str]]:
    album_name, input_path, is_dir = find_album_input(name)
    subdir = Path.cwd().name
    if subdir in NEW_META_DEFAULTS:
        ensure_meta_file(album_name, META_DIR, NEW_META_DEFAULTS[subdir])
    defaults, album_meta = load_meta(album_name, META_DIR)
    meta = merge_meta(defaults, album_meta)
    title, artist = resolve_title_artist(album_name, meta)
    year = meta.get("year", "")

    images = meta.get("images") or []
    if images:
        cover, artist_imgs = None, []
    else:
        # weekly-style lookup first (assets/<name>_cover.*), then the legacy
        # ost-style assets/<name>.*; artist photos from assets/artists/<name>.*
        # or per-album assets/<name>_artist*.*.
        cover = find_cover(album_name, subdir=subdir) or find_album_cover(
            album_name, subdir=subdir
        )
        artist_imgs = find_artist_images(
            album_name, album_artist_names(album_name), subdir=subdir
        )

    return (
        album_name,
        input_path,
        is_dir,
        meta,
        title,
        artist,
        year,
        images,
        cover,
        artist_imgs,
    )


def generate_chp_for_cover(name: str, input_path: Path, is_dir: bool) -> Path | None:
    if is_dir:
        audio_files, _, _ = collect_files(input_path)
        if not audio_files:
            safe_print(f"Error: no audio files in {input_path}")
            return None
        ensure_audio_output_dirs()
        chp_path = audio_paths_for(name)["chp"]
        generate_chapters(audio_files, chp_path)
        return chp_path

    chp_path = input_path.parent / f"{name}.mp3.chp"
    if not chp_path.exists():
        chp_path = Path(f"{name}.mp3.chp")
    if not chp_path.exists():
        safe_print(f"Error: chapter file not found for {name}")
        return None
    return chp_path


def build_typ_content(
    album_name: str,
    title: str,
    artist: str,
    year: str,
    images: list[str],
    cover: str | None,
    artist_imgs: list[str],
    chp_path: Path,
    subdir: str,
    meta: dict,
    lrc: str | None = None,
) -> str:
    if chp_path == audio_paths_for(album_name)["chp"]:
        chapters_path: str | None = f"/{subdir}/{OUTPUT_BASE}/{chp_path.name}"
    elif chp_path.parent.name == "medias":
        chapters_path = f"/{subdir}/medias/{chp_path.name}"
    else:
        chapters_path = f"/{subdir}/{chp_path.name}"

    return generate_typ(
        title, artist, year, images, cover, artist_imgs, chapters_path, lrc, meta
    )


def track_output_paths(album_name: str, stem: str) -> dict:
    return {
        "typ": Path(OUTPUT_BASE, "typs", album_name, f"{stem}.typ"),
        "pdf": Path(OUTPUT_BASE, "pdfs", album_name, f"{stem}.pdf"),
        "jpg": Path(OUTPUT_BASE, "jpgs", album_name, f"{stem}.jpg"),
    }


def find_track_lrc(input_dir: Path, audio_file: Path) -> Path | None:
    """Track LRC: exact stem match, else same leading track number."""
    exact = input_dir / f"{audio_file.stem}.lrc"
    if exact.exists():
        return exact
    audio_no = audio_file.stem.split(".", 1)[0].strip()
    if not audio_no:
        return None
    for candidate in sorted(input_dir.glob("*.lrc")):
        if candidate.stem.split(".", 1)[0].strip() == audio_no:
            return candidate
    return None


def generate_track_posters(
    album_name: str,
    input_path: Path,
    artist: str,
    year: str,
    images: list[str],
    cover: str | None,
    artist_imgs: list[str],
    meta: dict,
    subdir: str,
) -> int:
    """Per-track posters: cover left, the track's lyrics right (weekly-style).

    Tracks without an LRC are skipped; their slide falls back to the album
    poster in add_one.
    """
    audio_files, _, _ = collect_files(input_path)
    if not audio_files:
        safe_print(f"Error: no audio files in {input_path}")
        return 1

    status = 0
    for audio_file in audio_files:
        lrc_path = find_track_lrc(input_path, audio_file)
        if lrc_path is None:
            safe_print(f"Warning: no lrc for track {audio_file.name}, skipping poster")
            continue
        paths = track_output_paths(album_name, audio_file.stem)
        project_typ = PROJECT_ROOT / subdir / paths["typ"]
        project_pdf = PROJECT_ROOT / subdir / paths["pdf"]
        paths["typ"].parent.mkdir(parents=True, exist_ok=True)
        paths["pdf"].parent.mkdir(parents=True, exist_ok=True)
        paths["jpg"].parent.mkdir(parents=True, exist_ok=True)

        lrc_arg = f"/{subdir}/medias/{typ_str(album_name)}/{typ_str(lrc_path.name)}"
        content = generate_typ(
            lrc_path.stem,
            artist,
            year,
            images,
            cover,
            artist_imgs,
            None,
            lrc_arg,
            meta,
        )
        if write_typ_if_changed(paths["typ"], content):
            safe_print(f"Generated: {paths['typ']}")
        if not compile_typ(project_typ, project_pdf):
            status = 1
            continue
        if not pdf_to_jpg(paths["pdf"], paths["jpg"]):
            status = 1
            continue
        safe_print(f"Track poster ready: {paths['jpg']}")
    return status


def compile_one(name: str, subdir: str) -> int:
    paths = output_paths_for(name)
    project_typ = PROJECT_ROOT / subdir / paths["typ"]
    project_pdf = PROJECT_ROOT / subdir / paths["pdf"]
    if not compile_typ(project_typ, project_pdf):
        return 1
    if not pdf_to_jpg(paths["pdf"], paths["jpg"]):
        return 1
    safe_print(f"Draft ready: {paths['jpg']}")
    return 0


def typ_one(name: str) -> int:
    ensure_output_dirs()
    subdir = Path.cwd().name
    paths = output_paths_for(name)

    (
        album_name,
        input_path,
        is_dir,
        meta,
        title,
        artist,
        year,
        images,
        cover,
        artist_imgs,
    ) = load_album_context(name)
    chp_path = generate_chp_for_cover(album_name, input_path, is_dir)
    if chp_path is None:
        return 1

    # Singles: the overview poster doubles as the lyric poster.
    single_lrc = None
    if not is_dir:
        lrc_file = input_path.with_suffix(".lrc")
        if lrc_file.exists():
            single_lrc = f"/{subdir}/medias/{typ_str(lrc_file.name)}"

    typ_content = build_typ_content(
        album_name,
        title,
        artist,
        year,
        images,
        cover,
        artist_imgs,
        chp_path,
        subdir,
        meta,
        lrc=single_lrc,
    )
    if write_typ_if_changed(paths["typ"], typ_content):
        safe_print(f"Generated: {paths['typ']}")
    else:
        safe_print(f"Reusing existing typ: {paths['typ']}")

    if compile_one(album_name, subdir) != 0:
        return 1

    if is_dir:
        return generate_track_posters(
            album_name,
            input_path,
            artist,
            year,
            images,
            cover,
            artist_imgs,
            meta,
            subdir,
        )
    return 0


def merge_album_media(name: str, input_path: Path, is_dir: bool) -> Path | None:
    ensure_audio_output_dirs()
    paths = audio_paths_for(name)

    if is_dir:
        audio_files, lrc_files, lang_lrc = collect_files(input_path)
        if not audio_files:
            safe_print(f"Error: no audio files in {input_path}")
            return None

        concat_audio(audio_files, paths["mp3"])

        all_groups: dict[str, list[Path]] = {"": lrc_files}
        all_groups.update(lang_lrc)
        for lang, files in all_groups.items():
            if not files:
                continue
            stem = f"{name}{lang}" if lang else name
            merge_lrc_to_srt(
                files, audio_files, Path(OUTPUT_BASE, "srts", f"{stem}.srt")
            )
            merge_lang_lrc(files, audio_files, Path(OUTPUT_BASE, f"{stem}.lrc"))
    else:
        shutil.copy2(input_path, paths["mp3"])

    return paths["mp3"]


def chp_one(name: str) -> int:
    ctx = load_album_context(name)
    album_name, input_path, is_dir = ctx[0], ctx[1], ctx[2]
    chp_path = generate_chp_for_cover(album_name, input_path, is_dir)
    if chp_path is None:
        return 1
    safe_print(f"Chapters ready: {chp_path}")
    return 0


def build_track_slides(
    album_name: str, input_path: Path, album_jpg: Path
) -> list[tuple[Path, float]]:
    """One slide per track: the track poster (lyrics) if available, else the
    album overview poster; duration = the track's own audio length."""
    audio_files, _, _ = collect_files(input_path)
    slides = []
    for audio_file in audio_files:
        jpg = Path(OUTPUT_BASE, "jpgs", album_name, f"{audio_file.stem}.jpg")
        if not jpg.exists():
            jpg = album_jpg
        slides.append((jpg, get_duration(audio_file)))
    return slides


def add_one(name: str) -> int:
    if typ_one(name) != 0:
        return 1

    ctx = load_album_context(name)
    album_name, input_path, is_dir = ctx[0], ctx[1], ctx[2]
    mp3_path = merge_album_media(album_name, input_path, is_dir)
    if mp3_path is None:
        return 1

    paths = output_paths_for(name)
    if not mp3_path.exists():
        safe_print(f"Error: audio not found: {mp3_path}")
        return 1

    if is_dir:
        slides = build_track_slides(album_name, input_path, paths["jpg"])
        if not make_mp4_slides(slides, mp3_path, paths["mp4"]):
            return 1
    elif not make_mp4(paths["jpg"], mp3_path, paths["mp4"]):
        return 1
    safe_print(f"MP4 ready: {paths['mp4']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Album/OST video generator")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser(
        "chp", help="generate (or locate) the chapter file only, no cover/audio"
    ).add_argument("name")
    sub.add_parser(
        "typ", help="generate chapter file, typ, and cover pdf/jpg (no audio merge)"
    ).add_argument("name")
    sub.add_parser(
        "add", help="compile pdf/jpg/mp4 (reuse _output/typs/*.typ if present)"
    ).add_argument("name")

    args = parser.parse_args()
    name = strip_ext(args.name)

    if args.cmd == "chp":
        return chp_one(name)
    if args.cmd == "typ":
        return typ_one(name)
    if args.cmd == "add":
        return add_one(name)
    return 1


if __name__ == "__main__":
    sys.exit(main())
