"""Common helpers shared by music generators."""

from __future__ import annotations

import glob
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = SCRIPT_DIR.parent


def safe_print(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((msg + "\n").encode("utf-8", "replace"))


def run_checked(cmd: list[str], cwd: str | Path | None = None) -> bool:
    return subprocess.run(cmd, cwd=cwd, check=False).returncode == 0


def strip_ext(name: str) -> str:
    lower = name.lower()
    for ext in (".mp3", ".lrc", ".mp4", ".pdf", ".typ"):
        if lower.endswith(ext):
            return name[: -len(ext)]
    return name


def typ_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def write_typ_if_changed(output_path: Path, content: str) -> bool:
    if output_path.exists() and output_path.read_text(encoding="utf-8") == content:
        return False
    output_path.write_text(content, encoding="utf-8")
    return True


def find_cover(name: str, assets_dir: str = "assets", subdir: str = "") -> str | None:
    prefix = f"/{subdir}/" if subdir else "/"
    for ext in ("jpg", "jpeg", "png"):
        path = Path(assets_dir) / f"{name}_cover.{ext}"
        if path.exists():
            return f"{prefix}{assets_dir}/{path.name}"
    return None


def normalize_artist_name(name: str) -> str:
    """Normalize an artist name for shared artist image lookup."""
    return name.strip().rstrip(".")


def find_shared_artist_image(
    artist: str, assets_dir: str = "assets", subdir: str = ""
) -> str | None:
    prefix = f"/{subdir}/" if subdir else "/"
    artists_dir = Path(assets_dir) / "artists"
    if not artists_dir.exists():
        return None
    base = normalize_artist_name(artist)
    for ext in ("jpg", "jpeg", "png"):
        path = artists_dir / f"{base}.{ext}"
        if path.exists():
            return f"{prefix}{assets_dir}/artists/{path.name}"
    return None


def find_song_artist_images(
    name: str, assets_dir: str = "assets", subdir: str = ""
) -> list[str]:
    prefix = f"/{subdir}/" if subdir else "/"
    arts: list[str] = []
    for ext in ("jpg", "jpeg", "png"):
        arts.extend(glob.glob(str(Path(assets_dir) / f"{name}_artist*.{ext}")))
    arts.sort()
    return [f"{prefix}{assets_dir}/{Path(a).name}" for a in arts]


def find_artist_images(
    name: str,
    artist_names: Iterable[str] | None = None,
    assets_dir: str = "assets",
    subdir: str = "",
) -> list[str]:
    """Find artist images, preferring shared assets/artists/ over per-song files."""
    images: list[str] = []
    seen = set()

    if artist_names:
        for artist in artist_names:
            shared = find_shared_artist_image(artist, assets_dir, subdir)
            if shared and shared not in seen:
                images.append(shared)
                seen.add(shared)

    if not images:
        images = find_song_artist_images(name, assets_dir, subdir)

    return images


def parse_artist_names_from_song_name(name: str) -> list[str]:
    """Extract artist names from '<title> - <artist>' or '<title> - <a>, <b>'."""
    if " - " not in name:
        return []
    artist_part = name.split(" - ", 1)[1]
    return [normalize_artist_name(a) for a in artist_part.split(",")]


def compile_typ(typ_path: Path, pdf_path: Path, root: Path = PROJECT_ROOT) -> bool:
    safe_print(f"Compiling typst: {typ_path.name}")
    return run_checked(
        ["typst", "compile", "--root", ".", str(typ_path), str(pdf_path)],
        cwd=root,
    )


def pdf_to_jpg(pdf_path: Path, jpg_path: Path) -> bool:
    safe_print(f"Converting to JPG: {jpg_path.name}")
    return run_checked(
        [
            "magick",
            "-density",
            "300",
            f"{pdf_path}[0]",
            "-resize",
            "x1080",
            "-background",
            "white",
            "-alpha",
            "remove",
            "-quality",
            "90",
            str(jpg_path),
        ]
    )


def make_mp4(
    jpg_path: Path,
    audio_path: Path,
    mp4_path: Path,
    audio_codec: str = "copy",
) -> bool:
    safe_print(f"Creating MP4: {mp4_path.name}")
    cmd: list[str] = [
        "ffmpeg",
        "-nostdin",
        "-loop",
        "1",
        "-framerate",
        "1",
        "-i",
        str(jpg_path),
        "-i",
        str(audio_path),
        "-c:v",
        "libx264",
        "-tune",
        "stillimage",
        "-pix_fmt",
        "yuv420p",
        "-shortest",
        "-y",
    ]
    if audio_codec == "copy":
        cmd.extend(["-c:a", "copy"])
    else:
        cmd.extend(["-c:a", audio_codec])
    cmd.append(str(mp4_path))
    return run_checked(cmd)


def ensure_output_dirs(base: str = "_output") -> None:
    Path(base).mkdir(exist_ok=True)
    Path(base, "typs").mkdir(exist_ok=True)
    Path(base, "pdfs").mkdir(exist_ok=True)
    Path(base, "jpgs").mkdir(exist_ok=True)
    Path(base, "srts").mkdir(exist_ok=True)
