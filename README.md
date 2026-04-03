# yt-abs

Youtube Playlist Downloader for Audiobookshelf.

## Installation

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -e .
```

## Configuration

Create `config.yml` (or `config.yaml`) in project root with this structure:

```yaml
refresh_time: "1h"  # optional: repeat downloads every 1 hour (1h, 30min, 1d, 300s)
download_images: true  # optional: download video thumbnails (default: true)
archive_path: "/audiobookshelf/.yt-abs-archive.txt"  # optional, default is .yt-abs-archive.txt in /audiobookshelf

playlists:
  # minimal entry
  - url: "https://www.youtube.com/playlist?list=PL..."
  - url: "https://www.youtube.com/playlist?list=PL..."
    out_dir: "/audiobookshelf" # optional, default /audiobookshelf
    book_title: "My Book Title" # optional, will use playlist name if not set
    description: "Podcast series about beer" # optional, will be set to "" if nothing provided
    author: "Author Name" # optional, will be set to Unknown if not set
    latest_entries: 10 # optional, only download the latest X playlist items (newest items)
  - url: "https://www.youtube.com/playlist?list=PL..."
    out_dir: "/audiobookshelf"
    book_title: "Another Book"
    author: "Another Author"
```

## Usage

Run with default config file:

```bash
yt-abs
```

Use explicit config path / format override:

```bash
yt-abs --config config.yml --format m4a
```

## Docker

Build and run with Docker:

```bash
docker compose up --build
```

## Behavior

- Default format: `m4a`
- Supports `yt-dlp` download archive to avoid duplicates
- Outputs to `out_dir/<book_title>/<playlist_index> - <title>.m4a`
- Downloads video thumbnails as `<playlist_index> - <title>.(jpg|webp)` (configurable via `download_images`)
- Generates `metadata.json` per book with title/author/description
- Audiobookshelf-ready folder structure
- If `refresh_time` is set, downloads periodically; otherwise runs once
- Press Ctrl+C to stop periodic mode
