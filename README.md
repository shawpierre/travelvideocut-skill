# travelvideocut Skill

`travelvideocut` is a Codex/Claude-style skill for organizing travel footage.

It helps an agent:

- Rename raw clips to `YYYY-MM-DD_地点_内容_原序号.ext`.
- Preserve the original camera sequence number for reversible sorting.
- Create one same-day compilation per folder/date.
- Burn a short title subtitle onto each segment before joining clips.

## Contents

```text
.
├── SKILL.md
├── agents/
│   └── openai.yaml
└── scripts/
    └── daily_concat_with_title_subtitles.py
```

## Requirements

- Python 3.9+.
- `ffmpeg` and `ffprobe` available on `PATH`, or installed under Homebrew's common Cellar path.
- Pillow for subtitle PNG rendering.
- A system font that covers CJK glyphs (PingFang on macOS, Noto Sans CJK on Linux, Microsoft YaHei on Windows). Override with `--font`.

Install on macOS:

```bash
brew install ffmpeg
pip3 install --user Pillow
```

Install on Debian/Ubuntu:

```bash
sudo apt install ffmpeg fonts-noto-cjk
pip3 install --user Pillow
```

## Usage

Place this folder in your agent's skills directory (e.g. `~/.claude/skills/travelvideocut/`). Then ask the agent to use `travelvideocut` on a folder of trip videos.

After clips have been renamed, run:

```bash
python3 scripts/daily_concat_with_title_subtitles.py <video-root>
```

Common options:

```bash
# Only one trip folder
python3 scripts/daily_concat_with_title_subtitles.py <video-root> --folder 新加坡

# Only one date in that folder
python3 scripts/daily_concat_with_title_subtitles.py <video-root> --folder 新加坡 --date 2026-05-04

# Preview groups + labels without rendering
python3 scripts/daily_concat_with_title_subtitles.py <video-root> --dry-run

# Custom font (e.g. on Linux)
python3 scripts/daily_concat_with_title_subtitles.py <video-root> \
    --font /usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc

# 4K output
python3 scripts/daily_concat_with_title_subtitles.py <video-root> \
    --width 3840 --height 2160

# Preserve input frame rate (default forces 30 fps)
python3 scripts/daily_concat_with_title_subtitles.py <video-root> --fps 0
```

The script expects renamed files like:

```text
<root>/<folder>/YYYY-MM-DD_地点_内容_原序号.MP4
```

It writes finished daily compilations to:

```text
<root>/拼接成片/<folder>/YYYY-MM-DD_<folder>_按拍摄时间拼接.MP4
```

## Notes

- The original video files stay in place unless you explicitly move or delete them.
- Temporary labeled segments are written under `/private/tmp/travelvideocut_segments`.
- Completed temporary segments are reused, so interrupted runs can usually resume.
- Files that don't match the `YYYY-MM-DD_地点_内容_原序号` pattern are reported as `SKIPPED` and not processed.
