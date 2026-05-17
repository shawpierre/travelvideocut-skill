#!/usr/bin/env python3
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}


def find_binary(name: str) -> Path:
    found = shutil.which(name)
    if found:
        return Path(found)
    candidates = sorted(Path("/opt/homebrew/Cellar").glob(f"{name}/*/bin/{name}"))
    if candidates:
        return candidates[-1]
    app_candidates = sorted(Path("/Applications").glob(f"**/{name}"))
    if app_candidates:
        return app_candidates[0]
    raise SystemExit(f"Could not find {name}. Install ffmpeg or add it to PATH.")


FFMPEG = find_binary("ffmpeg")
FFPROBE = find_binary("ffprobe")


def parse_args():
    parser = argparse.ArgumentParser(description="Create daily travel-video compilations with title subtitles.")
    parser.add_argument("root", help="Root folder containing trip subfolders.")
    parser.add_argument("--folder", help="Only process this direct child folder.")
    parser.add_argument("--date", help="Only process this YYYY-MM-DD date.")
    parser.add_argument("--output-folder", default="拼接成片", help="Output folder name under root.")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--crf", default="21")
    parser.add_argument("--preset", default="veryfast")
    return parser.parse_args()


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
    content = " ".join(parts[2:-1]) if len(parts) > 3 else path.stem
    label = f"{parts[0]} {location} {content}".strip()
    return {"path": path, "folder": folder, "date": parts[0], "seq": seq, "label": label}


def probe(path: Path):
    cmd = [
        str(FFPROBE),
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type",
        "-of",
        "json",
        str(path),
    ]
    data = json.loads(subprocess.check_output(cmd, text=True))
    duration = float(data.get("format", {}).get("duration") or 0)
    has_audio = any(s.get("codec_type") == "audio" for s in data.get("streams", []))
    return duration, has_audio


def make_label_png(label_path: Path, label: str):
    label_path.parent.mkdir(parents=True, exist_ok=True)
    label_literal = json.dumps(label, ensure_ascii=False)
    path_literal = json.dumps(str(label_path), ensure_ascii=False)
    swift = f'''
import AppKit
let size = NSSize(width: 980, height: 96)
let label = {label_literal}
let paragraph = NSMutableParagraphStyle()
paragraph.alignment = .center
let image = NSImage(size: size)
image.lockFocus()
NSColor.clear.setFill()
NSRect(origin: .zero, size: size).fill()
let rounded = NSBezierPath(roundedRect: NSRect(x: 0, y: 0, width: size.width, height: size.height), xRadius: 16, yRadius: 16)
NSColor.black.withAlphaComponent(0.56).setFill()
rounded.fill()
var fontSize: CGFloat = 54
while fontSize > 34 {{
    let font = NSFont(name: "Arial-BoldMT", size: fontSize) ?? NSFont.boldSystemFont(ofSize: fontSize)
    let measured = (label as NSString).size(withAttributes: [.font: font])
    if measured.width <= size.width - 58 {{ break }}
    fontSize -= 2
}}
let attrs: [NSAttributedString.Key: Any] = [
    .font: NSFont(name: "Arial-BoldMT", size: fontSize) ?? NSFont.boldSystemFont(ofSize: fontSize),
    .foregroundColor: NSColor.white,
    .paragraphStyle: paragraph
]
label.draw(in: NSRect(x: 24, y: 14, width: size.width - 48, height: 68), withAttributes: attrs)
image.unlockFocus()
let rep = NSBitmapImageRep(data: image.tiffRepresentation!)!
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: {path_literal}))
'''
    env = dict(os.environ)
    env["SWIFT_MODULE_CACHE_PATH"] = "/private/tmp/swiftmodule"
    env["CLANG_MODULE_CACHE_PATH"] = "/private/tmp/swiftmodule"
    subprocess.run(["swift", "-"], input=swift, text=True, check=True, env=env)


def segment_filter(width: int, height: int, duration: float, has_audio: bool):
    video = (
        "[0:v:0]"
        f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        "setsar=1,fps=30,format=yuv420p[base];"
        "[1:v:0]format=rgba[label];"
        "[base][label]overlay=(W-w)/2:H-h-58:format=auto:shortest=1[v]"
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


def render_segment(args, root: Path, clip, part_index: int):
    duration, has_audio = probe(clip["path"])
    work_root = Path("/private/tmp/travelvideocut_segments") / root.name / clip["folder"] / clip["date"]
    work_root.mkdir(parents=True, exist_ok=True)
    label_path = work_root / f"label_{part_index:03d}.png"
    segment = work_root / f"{part_index:03d}_{clip['seq']:04d}.mp4"
    if segment.exists() and segment.stat().st_size > 1024 * 1024:
        print(f"SEGMENT SKIP {clip['folder']} {clip['date']} {part_index}/{clip['total']}")
        return segment
    make_label_png(label_path, clip["label"])
    tmp = work_root / f".{part_index:03d}_{clip['seq']:04d}.tmp.mp4"
    tmp.unlink(missing_ok=True)
    cmd = [
        str(FFMPEG), "-hide_banner", "-loglevel", "warning", "-stats", "-y", "-nostdin",
        "-i", str(clip["path"]),
        "-loop", "1", "-t", f"{duration:.6f}", "-i", str(label_path),
        "-filter_complex", segment_filter(args.width, args.height, duration, has_audio),
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", args.preset, "-crf", args.crf, "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        str(tmp),
    ]
    print(f"SEGMENT {clip['folder']} {clip['date']} {part_index}/{clip['total']} {clip['label']}")
    subprocess.run(cmd, check=True)
    tmp.rename(segment)
    return segment


def concat_segments(args, root: Path, folder: str, date: str, segments):
    out_dir = root / args.output_folder / folder
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"{date}_{folder}_按拍摄时间拼接.MP4"
    tmp = out_dir / f".{date}_{folder}_按拍摄时间拼接.tmp.MP4"
    tmp.unlink(missing_ok=True)
    list_file = segments[0].parent / "concat_list.txt"
    list_file.write_text("".join(f"file '{str(p).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n" for p in segments), encoding="utf-8")
    cmd = [
        str(FFMPEG), "-hide_banner", "-loglevel", "warning", "-stats", "-y", "-nostdin",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy", "-movflags", "+faststart", str(tmp),
    ]
    print(f"CONCAT {folder} {date} segments={len(segments)} -> {output}")
    subprocess.run(cmd, check=True)
    output.unlink(missing_ok=True)
    tmp.rename(output)
    print(f"DONE {output}")


def main():
    args = parse_args()
    root = Path(args.root).resolve()
    clips = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTS:
            clip = parse_clip(path, root, args.output_folder)
            if not clip:
                continue
            if args.folder and clip["folder"] != args.folder:
                continue
            if args.date and clip["date"] != args.date:
                continue
            clips.append(clip)
    groups = {}
    for clip in clips:
        groups.setdefault((clip["folder"], clip["date"]), []).append(clip)
    for (folder, date), group in sorted(groups.items()):
        group.sort(key=lambda c: (c["seq"], c["path"].name))
        for clip in group:
            clip["total"] = len(group)
        print(f"GROUP {folder} {date} clips={len(group)}")
        segments = [render_segment(args, root, clip, i + 1) for i, clip in enumerate(group)]
        concat_segments(args, root, folder, date, segments)


if __name__ == "__main__":
    main()
