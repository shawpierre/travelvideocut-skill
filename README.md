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

- macOS for the bundled subtitle PNG renderer, which uses Swift/AppKit.
- Python 3.9+.
- `ffmpeg` and `ffprobe` available on `PATH`, or installed under Homebrew's common Cellar path.

Install ffmpeg with Homebrew:

```bash
brew install ffmpeg
```

## Usage

Place this folder in your agent's skills directory. Then ask the agent to use `travelvideocut` on a folder of trip videos.

After clips have been renamed, run:

```bash
python3 scripts/daily_concat_with_title_subtitles.py <video-root>
```

Optional filters:

```bash
python3 scripts/daily_concat_with_title_subtitles.py <video-root> --folder 新加坡
python3 scripts/daily_concat_with_title_subtitles.py <video-root> --folder 新加坡 --date 2026-05-04
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
