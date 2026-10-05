"""Waveform-stack cover generator for cumaean tracks.

Audio-driven "Unknown Pleasures" style covers. Source audio lives in
CUMAEAN_SOURCE; only root-level .ogg files are used (_loop/ and _orig/
subdirectories excluded).
"""

# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy", "matplotlib"]
# ///

from __future__ import annotations

import argparse
import os
import struct
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.common import (
    PROJECT_ROOT,
    compile_typ,
    load_json,
    load_meta,
    make_mp4,
    merge_meta,
    run_checked,
    safe_print,
    strip_ext,
    typ_str,
    write_typ_if_changed,
)

SUBDIR = "cumaean"
META_DIR = Path("metadata")
OUTPUT_BASE = "_output"
WAVE_DIR = Path(OUTPUT_BASE, "waves")

SOURCE_ROOT = Path(
    os.environ.get("CUMAEAN_SOURCE", r"C:\Users\User\Local\Media\cdn_media_cumaean")
)
AUDIO_EXT = ".ogg"

FFMPEG_EXE = "ffmpeg"

SAMPLE_RATE = 16000
ROWS = 80
NFFT = 2048
HOP = 512
FMIN = 30.0
FMAX = 8000.0

LINE_POINTS = 1200
FIG_W = 8.0
FIG_H = 11.0
PNG_DPI = 150
SPACING = 1.0
BUMP_HEIGHT = 1.6
VPROFILE_SIGMA = 0.30
VPROFILE_FLOOR = 0.25
HWIN_SIGMA = 0.30
HWIN_FLOOR = 0.0
JITTER = 0.04
FLAT_THRESHOLD = 0.06
LOUD_FLOOR = 0.3
LOUD_POW = 0.5

DEFAULT_LINE_SIZE_PT = 9.9
DEFAULT_IMAGE_WIDTH_MM = 129.5
DEFAULT_FRAME_PAD_X_MM = 8.0
DEFAULT_FRAME_STROKE_PT = 0.4
PT_TO_MM = 25.4 / 72.0
CHAR_ADVANCE_EM = 0.5
LINE_FIT_SAFETY = 0.98


def fit_line_size(title: str, meta: dict) -> float | None:
    parts = [title]
    if meta.get("artist"):
        parts.extend(["by", meta["artist"]])
    if meta.get("license"):
        parts.extend(["/", meta["license"]])
    n = max(1, len(" ".join(parts)))
    try:
        size = float(meta.get("line-size", DEFAULT_LINE_SIZE_PT))
    except (TypeError, ValueError):
        size = DEFAULT_LINE_SIZE_PT
    image_w = float(meta.get("image-width", DEFAULT_IMAGE_WIDTH_MM))
    pad_x = float(meta.get("frame-pad-x", DEFAULT_FRAME_PAD_X_MM))
    stroke = float(meta.get("frame-stroke", DEFAULT_FRAME_STROKE_PT))
    content_mm = image_w - 2 * pad_x - 2 * stroke * PT_TO_MM
    per_char_mm = size * CHAR_ADVANCE_EM * PT_TO_MM
    max_chars = content_mm / per_char_mm
    if n <= max_chars:
        return None
    return round(size * max_chars / n * LINE_FIT_SAFETY, 1)


def list_sources() -> dict[str, Path]:
    found: dict[str, Path] = {}
    if not SOURCE_ROOT.is_dir():
        return found
    for p in sorted(SOURCE_ROOT.iterdir()):
        if p.is_file() and p.suffix.lower() == AUDIO_EXT:
            found.setdefault(p.stem.lower(), p)
    return found


def find_source(name: str) -> Path | None:
    return list_sources().get(name.lower())


def decode_audio(src: Path, wav_path: Path) -> bool:
    safe_print(f"Decoding audio: {src.name}")
    return run_checked(
        [
            FFMPEG_EXE,
            "-y",
            "-v",
            "error",
            "-i",
            str(src),
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            str(wav_path),
        ]
    )


def read_wav_mono(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        n = w.getnframes()
        width = w.getsampwidth()
        raw = w.readframes(n)
    if width == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    elif width == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"unsupported sample width: {width}")
    peak = np.max(np.abs(data))
    if peak > 0:
        data /= peak
    return data


def band_envelopes(data: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    window = np.hanning(NFFT).astype(np.float32)
    n_frames = max(1, 1 + (len(data) - NFFT) // HOP)
    idx = np.arange(NFFT)[None, :] + HOP * np.arange(n_frames)[:, None]
    idx = np.clip(idx, 0, len(data) - 1)
    frames = data[idx] * window
    spec = np.abs(np.fft.rfft(frames, axis=1))
    freqs = np.fft.rfftfreq(NFFT, 1.0 / SAMPLE_RATE)

    fmax = min(FMAX, SAMPLE_RATE / 2.0)
    edges = np.geomspace(FMIN, fmax, ROWS + 1)
    env = np.zeros((ROWS, n_frames), dtype=np.float32)
    for r in range(ROWS):
        m = (freqs >= edges[r]) & (freqs < edges[r + 1])
        if m.any():
            env[r] = spec[:, m].mean(axis=1)

    env = np.log1p(env)
    row_energy = env.mean(axis=1)
    top = float(row_energy.max())
    raw = row_energy / top if top > 0 else np.zeros_like(row_energy)
    weights = (LOUD_FLOOR + (1.0 - LOUD_FLOOR) * raw**LOUD_POW).astype(np.float32)

    env -= env.min(axis=1, keepdims=True)
    row_max = env.max(axis=1, keepdims=True)
    np.divide(env, row_max, out=env, where=row_max > 0)
    return env, weights


def render_wave_png(
    env: np.ndarray, weights: np.ndarray, out_png: Path, seed: int = 7
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rng = np.random.default_rng(seed)
    n_rows, n_cols = env.shape
    x = np.linspace(0.0, 1.0, LINE_POINTS)
    t = np.linspace(0.0, 1.0, n_cols)

    mid = (n_rows - 1) / 2.0
    vprof = VPROFILE_FLOOR + (1.0 - VPROFILE_FLOOR) * np.exp(
        -0.5 * ((np.arange(n_rows) - mid) / (VPROFILE_SIGMA * n_rows)) ** 2
    )
    hwin = HWIN_FLOOR + (1.0 - HWIN_FLOOR) * np.exp(
        -0.5 * ((x - 0.5) / HWIN_SIGMA) ** 2
    )

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=PNG_DPI)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    for r in range(n_rows - 1, -1, -1):
        e = env[r]
        total = float(e.sum())
        if total > 1e-6:
            centroid = float((t * e).sum() / total)
            target = 0.5 + rng.uniform(-JITTER, JITTER)
            xs = np.clip(x - (target - centroid), 0.0, 1.0)
            row = np.interp(xs, t, e)
        else:
            row = np.zeros_like(x)
        gain = rng.uniform(0.75, 1.0)
        y0 = r * SPACING
        amp = BUMP_HEIGHT * vprof[r] * gain * weights[r] * hwin * row
        flat = amp < FLAT_THRESHOLD
        if flat.all():
            continue
        curve = y0 + amp
        ax.fill_between(
            x, y0, curve, where=~flat, color="black", lw=0, interpolate=True
        )
        ax.plot(x, np.ma.masked_where(flat, curve), color="black", lw=0.8)

    ax.set_xlim(0, 1)
    ax.set_ylim(-1.5, n_rows - 1 + BUMP_HEIGHT + 0.5)
    ax.axis("off")
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, facecolor="white")
    plt.close(fig)


def generate_wave(name: str, src: Path, meta: dict) -> Path | None:
    out_png = WAVE_DIR / f"{name}.png"
    with tempfile.TemporaryDirectory() as td:
        wav_path = Path(td) / "src.wav"
        if not decode_audio(src, wav_path):
            return None
        data = read_wav_mono(wav_path)
    if len(data) < NFFT:
        data = np.pad(data, (0, NFFT - len(data)))
    env, weights = band_envelopes(data)
    seed = int(meta.get("seed", 7))
    safe_print(f"Rendering wave PNG: {out_png.name}")
    render_wave_png(env, weights, out_png, seed=seed)
    return out_png


def png_aspect(path: Path) -> float:
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise ValueError(f"not a PNG: {path}")
    w, h = struct.unpack(">II", head[16:24])
    return h / w


def load_credits() -> dict:
    return load_json(META_DIR / "credits.json")


def generate_typ(name: str, wave_rel: str, meta: dict) -> str:
    params = [
        f'  title: "{typ_str(name)}"',
        f'  wave: "{typ_str(wave_rel)}"',
    ]
    for key in (
        "artist",
        "license",
        "license-url",
        "page-size",
        "flipped",
        "image-width",
        "wave-aspect",
        "base-size",
        "line-size",
        "text-font",
        "block-gap",
        "page-margin-y",
        "frame-stroke",
        "frame-pad-y",
        "frame-pad-x",
    ):
        if key in meta and meta[key] not in (None, ""):
            value = meta[key]
            if isinstance(value, str):
                params.append(f'  {key}: "{typ_str(value)}"')
            elif key == "line-size":
                params.append(f"  {key}: {value}pt")
            else:
                params.append(f"  {key}: {value}")
    return (
        '#import "/scripts/templates/cumaean.typ": cumaean-cover\n\n'
        "#cumaean-cover(\n" + ",\n".join(params) + "\n)\n"
    )


def paths_for(name: str) -> dict:
    return {
        "typ": Path(OUTPUT_BASE, "typs", f"{name}.typ"),
        "pdf": Path(OUTPUT_BASE, "pdfs", f"{name}.pdf"),
        "jpg": Path(OUTPUT_BASE, "jpgs", f"{name}.jpg"),
        "mp4": Path(OUTPUT_BASE, f"{name}.mp4"),
        "wave": WAVE_DIR / f"{name}.png",
    }


def ensure_output_dirs() -> None:
    Path(OUTPUT_BASE).mkdir(exist_ok=True)
    Path(OUTPUT_BASE, "typs").mkdir(exist_ok=True)
    Path(OUTPUT_BASE, "pdfs").mkdir(exist_ok=True)
    Path(OUTPUT_BASE, "jpgs").mkdir(exist_ok=True)
    WAVE_DIR.mkdir(parents=True, exist_ok=True)


def project_path(local: Path) -> Path:
    return PROJECT_ROOT / SUBDIR / local


def compute_meta(name: str) -> dict:
    defaults, item_meta = load_meta(name, META_DIR)
    credit = load_credits().get(name.lower(), {})
    return credit | merge_meta(defaults, item_meta)


def write_typ(name: str, paths: dict, meta: dict) -> None:
    meta.setdefault("wave-aspect", round(png_aspect(paths["wave"]), 4))
    fitted = fit_line_size(name, meta)
    if fitted is not None:
        meta["line-size"] = fitted
    wave_rel = f"/{SUBDIR}/{paths['wave'].as_posix()}"
    typ_content = generate_typ(name, wave_rel, meta)
    if write_typ_if_changed(paths["typ"], typ_content):
        safe_print(f"Generated: {paths['typ']}")
    else:
        safe_print(f"Reusing existing typ: {paths['typ']}")


def generate_typ_file(name: str) -> int:
    ensure_output_dirs()
    paths = paths_for(name)

    src = find_source(name)
    if not src:
        safe_print(f"Error: source not found for {name} in {SOURCE_ROOT}")
        return 1

    meta = compute_meta(name)

    if not generate_wave(name, src, meta):
        safe_print(f"Error: failed to render wave PNG for {name}")
        return 1
    write_typ(name, paths, meta)
    return 0


def refresh_typ(name: str) -> int:
    ensure_output_dirs()
    paths = paths_for(name)
    meta = compute_meta(name)
    if not paths["wave"].exists():
        src = find_source(name)
        if not src:
            safe_print(f"Error: source not found for {name} in {SOURCE_ROOT}")
            return 1
        if not generate_wave(name, src, meta):
            safe_print(f"Error: failed to render wave PNG for {name}")
            return 1
    write_typ(name, paths, meta)
    return 0


def compile_one(name: str) -> int:
    paths = paths_for(name)
    project_typ = project_path(paths["typ"])
    project_pdf = project_path(paths["pdf"])
    project_png = project_pdf.with_suffix(".png")

    if not compile_typ(project_typ, project_pdf):
        return 1

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


def add_one(name: str) -> int:
    paths = paths_for(name)

    if paths["typ"].exists():
        if refresh_typ(name) != 0:
            return 1
        if compile_one(name) != 0:
            return 1
    else:
        if typ_one(name) != 0:
            return 1

    src = find_source(name)
    if not src:
        safe_print(f"Error: source not found for {name}")
        return 1

    if not make_mp4(paths["jpg"], src, paths["mp4"], audio_codec="aac"):
        return 1
    safe_print(f"MP4 ready: {paths['mp4']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Waveform-stack cover video generator for cumaean tracks"
    )
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
