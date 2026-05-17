---
name: travelvideocut
description: Rename travel video clips by shooting date, location, and visible content, then create one same-day compilation per folder/date with burned-in title subtitles. Use when a user asks to organize trip footage, batch rename DJI/phone/action-camera videos, make daily travel video compilations, or add clip-title subtitles to joined travel footage.
---

# travelvideocut

Use this skill for two linked travel-video cleanup tasks:

1. Rename raw clips to `YYYY-MM-DD_地点_内容_原序号.ext`.
2. Join clips from each subfolder and date in shooting order, burning a subtitle on each segment from the renamed title: `YYYY-MM-DD 地点 内容`.

Keep original clips in place unless the user explicitly asks to move or delete them. Write finished compilations to a new output folder.

## Requirements

- `ffmpeg` and `ffprobe` on `PATH`, or installed under Homebrew's common Cellar path.
- Python 3.9+ and Pillow: `pip3 install --user Pillow`.
- A system font that covers CJK glyphs. The bundled script auto-discovers common fonts (macOS PingFang, Linux Noto Sans CJK / WenQuanYi, Windows Microsoft YaHei / SimHei). Pass `--font /path/to/font.ttf` to override.

## Workflow

1. Inventory video files with `rg --files` or `find`, scoped to common video extensions.
2. Extract reliable dates from original filenames first, especially DJI names like `DJI_20260504152445_0284_D_A01.MP4`; use media metadata only as a fallback.
3. Generate visual contact sheets before renaming. Prefer actual frame thumbnails over old names. If Quick Look, ffmpeg, or AVFoundation fails on a few files, name those conservatively from adjacent clips and time order.
4. Rename with a reversible pattern:
   - `YYYY-MM-DD_地点_内容_原序号.MP4`
   - Preserve the original sequence number at the end.
   - Keep content labels short, visual, and useful for editing, for example `云雾林瀑布入口`, `陶溪川市集摊位`, `滨海湾城市天际线`.
5. Validate rename results:
   - Total video count is unchanged.
   - No original camera-prefix files remain unless intentionally skipped.
   - No duplicate target names exist.
6. Run the bundled `scripts/daily_concat_with_title_subtitles.py` after clips are renamed. It groups clips by subfolder and date, sorts by the preserved original sequence number, burns title subtitles, and writes daily compilations.

## Subtitle Rule

For each source clip named:

```text
2026-05-04_新加坡_滨海湾城市天际线_0284.MP4
```

Burn this subtitle into that clip's segment:

```text
2026-05-04 新加坡 滨海湾城市天际线
```

Do not include `Part-x` or the final original sequence number in subtitles unless the user explicitly asks for it.

## Daily Compilation Script

Resolve bundled files relative to this `SKILL.md`. Use the bundled script after renaming:

```bash
python3 scripts/daily_concat_with_title_subtitles.py <video-root>
```

Common options:

```bash
# Only one trip folder
python3 scripts/daily_concat_with_title_subtitles.py <video-root> --folder 新加坡

# Only one date inside that folder
python3 scripts/daily_concat_with_title_subtitles.py <video-root> --folder 新加坡 --date 2026-05-04

# Preview what would be processed without rendering
python3 scripts/daily_concat_with_title_subtitles.py <video-root> --dry-run

# Override font (e.g. for Linux/Windows or a custom font)
python3 scripts/daily_concat_with_title_subtitles.py <video-root> \
    --font /usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc

# 4K output with proportionally scaled subtitle
python3 scripts/daily_concat_with_title_subtitles.py <video-root> \
    --width 3840 --height 2160

# Preserve input frame rate (default forces 30 fps)
python3 scripts/daily_concat_with_title_subtitles.py <video-root> --fps 0
```

Expected input naming:

```text
<root>/<folder>/YYYY-MM-DD_地点_内容_原序号.MP4
```

Default output:

```text
<root>/拼接成片/<folder>/YYYY-MM-DD_<folder>_按拍摄时间拼接.MP4
```

The script uses ffmpeg/ffprobe, creates temporary labeled segments under `/private/tmp/travelvideocut_segments`, and resumes by skipping completed segments.

## Practical Notes

- If `ffmpeg` is not on `PATH`, the script also searches `/opt/homebrew/Cellar/ffmpeg/*/bin/ffmpeg` and `/usr/local/Cellar/...`.
- If hardware encoding fails on macOS (`h264_videotoolbox` errors such as `-12908`), the script defaults to `libx264`; it is slower but stable.
- For long 4K HEVC clips, expect software encoding to take a while. Give progress updates and keep the process resumable.
- If the user interrupts, stop ffmpeg with `killall ffmpeg`, then rerun the script with `--folder` or `--date`; completed temporary segments are reused.
- Run with `--dry-run` first on a new dataset to confirm the grouping and labels before committing to a long render.
- Before final delivery, sample at least one exported frame to confirm the subtitle text, position, and date/content extraction.
