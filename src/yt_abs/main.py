"""Core implementation for yt-abs command."""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import yaml
from yt_dlp import YoutubeDL


DEFAULT_CONFIG_FILES = ["config.yml", "config.yaml"]
DEFAULT_FORMAT = "m4a"
DEFAULT_ARCHIVE = "/audiobookshelf/.yt-abs-archive.txt"


def parse_refresh_time(time_str: str) -> int:
    """Parse time string like '1h', '30min', '1d' into seconds."""
    match = re.match(r'^(\d+)([hdms])$', time_str.lower())
    if not match:
        raise ValueError(f"Invalid refresh_time format: {time_str}. Use e.g. '1h', '30min', '1d', '300s'")
    
    num, unit = match.groups()
    num = int(num)
    
    multipliers = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 86400,
    }
    
    if unit not in multipliers:
        raise ValueError(f"Unknown time unit: {unit}")
    
    return num * multipliers[unit]


def load_config(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if not isinstance(cfg, dict) or "playlists" not in cfg:
        raise ValueError("Config must contain 'playlists' key")

    return cfg


def find_config(path: Path):
    if path.is_file():
        return path

    for name in DEFAULT_CONFIG_FILES:
        candidate = path / name
        if candidate.exists():
            return candidate

    raise FileNotFoundError("No config file found in current directory (config.yml or config.yaml)")


def download_playlist(entry, default_format: str, archive_path: Path, download_thumbnails: bool = True):
    url = entry.get("url")
    if not url:
        raise ValueError("Each playlist entry must specify 'url'")

    out_dir = Path(entry.get("out_dir", "/audiobookshelf"))
    out_dir.mkdir(parents=True, exist_ok=True)

    # Map each playlist to a book directory to align with Audiobookshelf structure
    book_title = entry.get("book_title") or "%(playlist_title)s"
    book_dir = out_dir / book_title
    book_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "title": book_title,
        "author": entry.get("author", "Unknown"),
        "description": entry.get("description", ""),
    }
    metadata_file = book_dir / "metadata.json"
    if not metadata_file.exists():
        metadata_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    ydl_opts = {
        "format": f"bestaudio[ext={default_format}]/bestaudio/best",
        "outtmpl": str(book_dir / "%(playlist_index)03d - %(title)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": default_format,
                "preferredquality": "192",
            },
            
        ],
        "ignoreerrors": True,
        "quiet": False,
        "no_warnings": False,
        "restrictfilenames": False,
        'merge_output_format': 'm4a',
        "download_archive": str(archive_path),
    }

    if download_thumbnails:
        ydl_opts["write_thumbnail"] = True
        ydl_opts["postprocessors"].append({
            "key": "FFmpegMetadata",
            "add_metadata": True
        })
        ydl_opts["postprocessors"].append({
                "key": "EmbedThumbnail",
                'already_have_thumbnail': False, # avoid re-downloading thumbnail if it already exists
        })

    print(f"Downloading playlist {url} to {book_dir} as {default_format} {'with thumbnails' if download_thumbnails else 'without images'} (archive={archive_path})...")

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def main(argv=None):
    parser = argparse.ArgumentParser(description="yt-abs: Youtube -> Audiobookshelf playlist downloader")
    parser.add_argument("--config", type=str, default=None, help="Path to YAML config file (default: config.yml or config.yaml)")
    parser.add_argument("--format", type=str, default=DEFAULT_FORMAT, help="Audio format, default m4a")
    args = parser.parse_args(argv or sys.argv[1:])

    if args.config:
        config_path = Path(args.config)
    else:
        config_path = find_config(Path.cwd())

    config = load_config(config_path)
    playlists = config.get("playlists", [])
    archive = config.get("archive_path") or DEFAULT_ARCHIVE
    archive_path = Path(archive)

    if archive_path.exists() and archive_path.is_dir():
        # avoid passing a directory to yt-dlp archive param
        archive_path = archive_path / ".yt-abs-archive.txt"

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.touch(exist_ok=True)

    if not playlists:
        raise ValueError("'playlists' is empty in config")

    download_thumbnails = config.get("download_thumbnails", True)

    refresh_time_str = config.get("refresh_time")
    if refresh_time_str:
        refresh_seconds = parse_refresh_time(refresh_time_str)
        print(f"Starting periodic download every {refresh_time_str} ({refresh_seconds} seconds)")
    else:
        refresh_seconds = None

    try:
        while True:
            for playlist in playlists:
                download_playlist(playlist, default_format=args.format, archive_path=archive_path, download_thumbnails=download_thumbnails)
            
            if refresh_seconds is None:
                break
            
            print(f"Waiting {refresh_time_str} before next update...")
            time.sleep(refresh_seconds)
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting.")
        sys.exit(0)
