#!/usr/bin/env python3
"""Daily travel-video compilations with title subtitles.

Reads renamed clips of the form
    <root>/<folder>/YYYY-MM-DD_地点_内容_原序号.MP4
groups them by folder + date, sorts by original sequence number, burns a
short title subtitle on each clip, and concatenates each group into one
daily compilation under <root>/拼接成片/<folder>/.

Cross-platform (macOS / Linux / Windows). Requires:
    - ffmpeg, ffprobe on PATH (or under Homebrew Cellar)
    - Python 3.9+
    - Pillow  (pip3 install --user Pillow)
    - A system font that covers CJK (auto-discovered; --font to override)
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}

# All label-graphic sizes are scaled from this reference output height.
REF_HEIGHT = 1080


# ---------------------------------------------------------------------------
# Binary + font discovery
# ---------------------------------------------------------------------------

def find_binary(name: str) -> Path:
    """Locate ffmpeg/ffprobe on PATH or in common install locations."""
    found = shutil.which(name)
    if found:
        return Path(found)
    for prefix in ("/opt/homebrew/Cellar", "/usr/local/Cellar"):
        cands = sorted(Path(prefix).glob(f"{name}/*/bin/{name}"))
        if cands:
            return cands[-1]
    app_cands = sorted(Path("/Applications").glob(f"**/{name}"))
    if app_cands:
        return app_cands[0]
    raise SystemExit(f"Could not find {name}. Install ffmpeg or add it to PATH.")


def discover_cjk_font() -> str | None:
    """Return path to a system font that covers CJK glyphs, or None."""
    candidates = [
        # macOS
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        # Linux (Debian/Ubuntu, Fedora, Arch)
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        # Windows
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Create daily travel-video compilations with title subtitles.")
    parser.add_argument("root", help="Root folder containing trip subfolders.")
    parser.add_argument("--folder", help="Only process this direct child folder.")
    parser.add_argument("--date", help="Only process this YYYY-MM-DD date.")
    parser.add_argument("--output-folder", default="拼接成片",
                        help="Output folder name under root.")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=30,
                        help="Force output fps. Pass 0 to preserve input fps.")
    parser.add_argument("--crf", default="21")
    parser.add_argument("--preset", default="veryfast")
    parser.add_argument("--font",
                        help="Path to a TTF/TTC/OTF font with CJK glyphs.")
    parser.add_argument("--subtitle-margin", type=int, default=None,
                        help="Bottom margin of the subtitle box, in output pixels.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the groups and clips that would be rendered, then exit.")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Clip parsing
# ---------------------------------------------------------------------------

def parse_clip(path: Path, root: Path, output_folder: str):
    rel = path.relative_to(root)
    if rel.parts and rel.parts[0] == output_folder:
        return None
    if len(rel.parts) < 2:
        return None
    folder = rel.parts[0]
    parts = path.stem.split("_")
    if not parts or not re.match(r"^\d{4}-\d{2}-\d{2}$", parts[0]):
        return None
    try:
        seq = int(parts[-1])
    except ValueError:
        seq = 0
    location = parts[1] if len(parts) > 1 else folder
    # Content tokens are everything between location and trailing sequence number.
    content = " ".join(parts[2:-1]) if len(parts) > 3 else ""
    label = " ".join(p for p in (parts[0], location, content) if p).strip()
    return {"path": path, "folder": folder, "date": parts[0], "seq": seq, "label": label}


# ---------------------------------------------------------------------------
# Media probing
# ---------------------------------------------------------------------------

def probe(ffprobe: Path, path: Path):
    cmd = [
        str(ffprobe), "-v", "error",
        "-show_entries", "format=duration:stream=codec_type",
        "-of", "json", str(path),
    ]
    data = json.loads(subprocess.check_output(cmd, text=True))
    duration = float(data.get("format", {}).get("duration") or 0)
    has_audio = any(s.get("codec_type") == "audio" for s in data.get("streams", []))
    return duration, has_audio


# ---------------------------------------------------------------------------
# Label graphic
# ---------------------------------------------------------------------------

def label_geometry(width: int, height: int, margin):
    """Return label-PNG dimensions scaled from the reference 1080p layout."""
    scale = height / REF_HEIGHT
    return dict(
        img_w=max(320, int(width * 0.51)),
        img_h=max(48, int(96 * scale)),
        pad_x=max(12, int(24 * scale)),
        radius=max(8, int(16 * scale)),
        fontsize_max=max(20, int(54 * scale)),
        fontsize_min=max(14, int(34 * scale)),
        bottom_margin=margin if margin is not None else max(20, int(58 * scale)),
    )


def make_label_png(label_path: Path, label: str, geo: dict, font_file: str):
    """Render a translucent rounded-rect label using Pillow."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise SystemExit(
            "Pillow is required for label rendering.\n"
            "Install with: pip3 install --user Pillow")

    def load_font(size):
        # PingFang.ttc index 5 is roughly Semibold; fall back to index 0.
        for idx in (5, 0):
            try:
                return ImageFont.truetype(font_file, size, index=idx)
            except (OSError, ValueError):
                continue
        return ImageFont.truetype(font_file, size)

    img_w, img_h = geo["img_w"], geo["img_h"]
    pad_x, radius = geo["pad_x"], geo["radius"]

    image = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    fontsize = geo["fontsize_max"]
    font = load_font(fontsize)
    while fontsize > geo["fontsize_min"]:
        bbox = draw.textbbox((0, 0), label, font=font)
        text_w = bbox[2] - bbox[0]
        if text_w <= img_w - 2 * pad_x:
            break
        fontsize -= 2
        font = load_font(fontsize)

    bbox = draw.textbbox((0, 0), label, font=font)
    text_w = bbox[2] - bbox[0]

    # Background pill: fits text + padding, but never exceeds img_w.
    box_w = min(img_w, text_w + 2 * pad_x)
    box_x = (img_w - box_w) // 2
    draw.rounded_rectangle(
        [(box_x, 0), (box_x + box_w, img_h)],
        radius=radius,
        fill=(0, 0, 0, 143),  # ≈ 0.56 alpha to match the previous look
    )

    draw.text(
        (img_w / 2, img_h / 2), label,
        fill=(255, 255, 255, 255),
        font=font,
        anchor="mm",
    )

    label_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(label_path, "PNG")


# ---------------------------------------------------------------------------
# Segment rendering
# ---------------------------------------------------------------------------

def segment_filter(args, geo, duration: float, has_audio: bool):
    fps_filter = f",fps={args.fps}" if args.fps and args.fps > 0 else ""
    overlay_y = f"H-h-{geo['bottom_margin']}"
    video = (
        "[0:v:0]"
        f"scale={args.width}:{args.height}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={args.width}:{args.height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1{fps_filter},format=yuv420p[base];"
        "[1:v:0]format=rgba[label];"
        f"[base][label]overlay=(W-w)/2:{overlay_y}:format=auto:shortest=1[v]"
    )
    if has_audio:
        audio = (
            "[0:a:0]aresample=48000,"
            "aformat=sample_rates=48000:channel_layouts=stereo,"
            "apad,"
            f"atrim=0:duration={duration:.6f},"
            "asetpts=PTS-STARTPTS[a]"
        )
    else:
        audio = (
            "anullsrc=channel_layout=stereo:sample_rate=48000,"
            f"atrim=0:duration={duration:.6f},"
            "asetpts=PTS-STARTPTS[a]"
        )
    return video + ";" + audio


def render_segment(args, ffmpeg, ffprobe, geo, font_file, root: Path, clip, part_index: int):
    duration, has_audio = probe(ffprobe, clip["path"])
    work_root = (
        Path("/private/tmp/travelvideocut_segments")
        / root.name / clip["folder"] / clip["date"]
    )
    work_root.mkdir(parents=True, exist_ok=True)
    label_path = work_root / f"label_{part_index:03d}.png"
    segment = work_root / f"{part_index:03d}_{clip['seq']:04d}.mp4"

    if segment.exists() and segment.stat().st_size > 1024 * 1024:
        print(f"SEGMENT SKIP {clip['folder']} {clip['date']} "
              f"{part_index}/{clip['total']}")
        return segment

    make_label_png(label_path, clip["label"], geo, font_file)
    tmp = work_root / f".{part_index:03d}_{clip['seq']:04d}.tmp.mp4"
    tmp.unlink(missing_ok=True)
    cmd = [
        str(ffmpeg), "-hide_banner", "-loglevel", "warning", "-stats", "-y", "-nostdin",
        "-i", str(clip["path"]),
        "-loop", "1", "-t", f"{duration:.6f}", "-i", str(label_path),
        "-filter_complex", segment_filter(args, geo, duration, has_audio),
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", args.preset, "-crf", args.crf, "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        str(tmp),
    ]
    print(f"SEGMENT {clip['folder']} {clip['date']} "
          f"{part_index}/{clip['total']} {clip['label']}")
    subprocess.run(cmd, check=True)
    tmp.rename(segment)
    return segment


def concat_segments(args, ffmpeg, root: Path, folder: str, date: str, segments):
    out_dir = root / args.output_folder / folder
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"{date}_{folder}_按拍摄时间拼接.MP4"
    tmp = out_dir / f".{date}_{folder}_按拍摄时间拼接.tmp.MP4"
    tmp.unlink(missing_ok=True)
    list_file = segments[0].parent / "concat_list.txt"
    # ffmpeg concat needs single-quotes around each path; escape any embedded quote.
    list_file.write_text(
        "".join(
            "file '{}'\n".format(str(p).replace("'", r"'\''"))
            for p in segments
        ),
        encoding="utf-8",
    )
    cmd = [
        str(ffmpeg), "-hide_banner", "-loglevel", "warning", "-stats", "-y", "-nostdin",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy", "-movflags", "+faststart", str(tmp),
    ]
    print(f"CONCAT {folder} {date} segments={len(segments)} -> {output}")
    subprocess.run(cmd, check=True)
    output.unlink(missing_ok=True)
    tmp.rename(output)
    print(f"DONE {output}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    root = Path(args.root).resolve()

    if args.dry_run:
        ffmpeg = ffprobe = None
        font_file = args.font  # may be None; OK for dry run
    else:
        ffmpeg = find_binary("ffmpeg")
        ffprobe = find_binary("ffprobe")
        font_file = args.font or discover_cjk_font()
        if not font_file:
            raise SystemExit(
                "No CJK-capable font found on this system. "
                "Pass --font /path/to/font.ttf, or install one "
                "(macOS: PingFang; Linux: Noto Sans CJK; Windows: Microsoft YaHei).")
        if not Path(font_file).exists():
            raise SystemExit(f"--font path does not exist: {font_file}")

    geo = label_geometry(args.width, args.height, args.subtitle_margin)

    clips, skipped = [], []
    for path in root.rglob("*"):
        if not (path.is_file() and path.suffix.lower() in VIDEO_EXTS):
            continue
        clip = parse_clip(path, root, args.output_folder)
        if not clip:
            # Don't flag files already written into the output folder.
            try:
                rel = path.relative_to(root)
                if rel.parts and rel.parts[0] == args.output_folder:
                    continue
            except ValueError:
                pass
            skipped.append(path)
            continue
        if args.folder and clip["folder"] != args.folder:
            continue
        if args.date and clip["date"] != args.date:
            continue
        clips.append(clip)

    if skipped:
        print(f"SKIPPED {len(skipped)} files not matching "
              "YYYY-MM-DD_地点_内容_原序号 pattern:")
        for p in skipped[:10]:
            print(f"  - {p.relative_to(root)}")
        if len(skipped) > 10:
            print(f"  ... and {len(skipped) - 10} more.")

    groups = {}
    for clip in clips:
        groups.setdefault((clip["folder"], clip["date"]), []).append(clip)

    if not groups:
        print("No matching clips found.")
        return

    for (folder, date), group in sorted(groups.items()):
        group.sort(key=lambda c: (c["seq"], c["path"].name))
        for clip in group:
            clip["total"] = len(group)
        print(f"GROUP {folder} {date} clips={len(group)}")

        if args.dry_run:
            for i, clip in enumerate(group, 1):
                print(f"  [{i:03d}] seq={clip['seq']:04d}  {clip['label']}")
            continue

        segments = [
            render_segment(args, ffmpeg, ffprobe, geo, font_file, root, clip, i + 1)
            for i, clip in enumerate(group)
        ]
        concat_segments(args, ffmpeg, root, folder, date, segments)


if __name__ == "__main__":
    main()
