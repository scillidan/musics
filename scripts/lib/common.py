"""Common helpers shared by music generators."""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = SCRIPT_DIR.parent

_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def _expand_vars(value: str) -> str:
    """Expand ${VAR} placeholders from the environment (left as-is if unset)."""
    return _VAR_RE.sub(lambda m: os.environ.get(m.group(1), m.group(0)), value)


def load_dotenv(*paths: Path) -> None:
    for path in paths:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(
                key.strip(), _expand_vars(value.strip().strip('"').strip("'"))
            )


def safe_print(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((msg + "\n").encode("utf-8", "replace"))


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        safe_print(f"Error: invalid JSON {path}: {e}")
        sys.exit(1)


def load_meta(
    name: str, meta_dir: Path, default_config: str = "_default.json"
) -> tuple[dict, dict]:
    if not meta_dir.exists():
        return {}, {}
    defaults = load_json(meta_dir / default_config)
    item = load_json(meta_dir / f"{name}.json")
    return defaults, item


def ensure_meta_file(name: str, meta_dir: Path, defaults: dict | None = None) -> Path:
    """Create meta_dir/<name>.json from defaults if it does not exist yet."""
    meta_dir.mkdir(parents=True, exist_ok=True)
    path = meta_dir / f"{name}.json"
    if not path.exists():
        path.write_text(
            json.dumps(defaults or {}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        safe_print(f"Created metadata: {path}")
    return path


def merge_meta(defaults: dict, item: dict) -> dict:
    return defaults | item


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


def get_media_duration(path: Path) -> float | None:
    """Return media duration in seconds via ffprobe, or None if unavailable."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


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
        "10",
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
    ]
    # Give the output an explicit duration instead of relying on -shortest.
    # The video is a looped still image; with -shortest, ffmpeg stops emitting
    # video frames as soon as the audio decoder hits EOF, so the video stream can
    # end several seconds before the audio stream. Players that use the video
    # track length as the presentation timeline then cut the song off early.
    # Passing -t keeps the video track covering the whole audio; 10 fps keeps the
    # video/audio track lengths within one frame of each other.
    duration = get_media_duration(audio_path)
    if duration is not None:
        # +0.1s (one frame at 10 fps) rounds the video up so it always covers
        # the audio track instead of ending a frame short.
        cmd.extend(["-t", f"{duration + 0.1:.3f}"])
    else:
        cmd.append("-shortest")
    cmd.append("-y")
    if audio_codec == "copy":
        cmd.extend(["-c:a", "copy"])
    else:
        cmd.extend(["-c:a", audio_codec])
    cmd.append(str(mp4_path))
    return run_checked(cmd)


def make_mp4_slides(
    slides: list[tuple[Path, float]],
    audio_path: Path,
    mp4_path: Path,
    fps: int = 10,
) -> bool:
    """Create an MP4 that switches still image at each slide boundary.

    slides: list of (jpg_path, duration_seconds) in playback order. The video
    track length equals the sum of durations, so with per-track chapter
    durations it stays in sync with a concatenated audio track.
    """
    if not slides:
        safe_print("Error: no slides given")
        return False
    total = sum(d for _, d in slides)
    safe_print(f"Creating MP4 with {len(slides)} slides: {mp4_path.name}")
    list_path = mp4_path.parent / f".{mp4_path.stem}_slides.txt"
    lines: list[str] = []
    for jpg, duration in slides:
        lines.append(f"file '{jpg.resolve()}'")
        lines.append(f"duration {duration:.3f}")
    lines.append(f"file '{slides[-1][0].resolve()}'")
    list_path.write_text("\n".join(lines), encoding="utf-8")
    try:
        return run_checked(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-i",
                str(audio_path),
                "-vf",
                f"fps={fps},format=yuv420p",
                "-c:v",
                "libx264",
                "-tune",
                "stillimage",
                "-c:a",
                "copy",
                "-t",
                f"{total + 0.1:.3f}",
                str(mp4_path),
            ]
        )
    finally:
        list_path.unlink(missing_ok=True)


def ensure_output_dirs(base: str = "_output") -> None:
    Path(base).mkdir(exist_ok=True)
    Path(base, "typs").mkdir(exist_ok=True)
    Path(base, "pdfs").mkdir(exist_ok=True)
    Path(base, "jpgs").mkdir(exist_ok=True)
    Path(base, "srts").mkdir(exist_ok=True)
