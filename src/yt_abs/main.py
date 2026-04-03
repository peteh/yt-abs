"""Core implementation for yt-abs command."""

import argparse
import json
import re
import sys
import time
import os
import urllib.request
from pathlib import Path

import yaml
from yt_dlp import YoutubeDL


DEFAULT_CONFIG_FILES = ["config.yml", "config.yaml"]
DEFAULT_FORMAT = "m4a"
DEFAULT_ARCHIVE = "/audiobookshelf/.yt-abs-archive.txt"


def extract_playlist_info(playlist_url: str):
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
    }

    with YoutubeDL(ydl_opts) as ydl: # type: ignore
        return ydl.extract_info(playlist_url, download=False)


def get_channel_url(info: dict):
    """
    Try to get the playlist owner channel URL.
    Fallback: derive from first valid entry (not guaranteed correct).
    """

    # 1. Direct metadata (preferred)
    channel_url = info.get("channel_url") or info.get("uploader_url")
    if channel_url:
        return channel_url

    # 2. Fallback: first valid entry
    for entry in info.get("entries", []):
        if not entry:
            continue

        entry_channel = entry.get("channel_url") or entry.get("uploader_url")
        if entry_channel:
            return entry_channel

    return None


def extract_channel_avatar(channel_url: str):
    ydl_opts : dict[str, object] = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,  # critical: no deep traversal
        "playlistend": 1,  # hard stop if treated as playlist
        "noplaylist": True,  # avoid channel video listing
    }

    with YoutubeDL(ydl_opts) as ydl: # type: ignore
        info = ydl.extract_info(channel_url, download=False)

    thumbnails = info.get("thumbnails", [])
    if not thumbnails:
        return None

    best = max(thumbnails, key=lambda x: x.get("height", 0))
    return best.get("url")


def download_image(url: str, output_path: str):
    if not url:
        raise ValueError("No image URL to download")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    urllib.request.urlretrieve(url, output_path)


def download_playlist_author_avatar(playlist_url: str, output_file: str):
    # Step 1: playlist metadata
    playlist_info = extract_playlist_info(playlist_url)

    # Step 2: resolve channel
    channel_url = get_channel_url(playlist_info)  # type: ignore
    if not channel_url:
        raise RuntimeError("Could not determine channel URL from playlist")

    print(f"Channel URL: {channel_url}")

    # Step 3: extract avatar
    avatar_url = extract_channel_avatar(channel_url)
    if not avatar_url:
        raise RuntimeError("Could not find channel avatar")

    print(f"Avatar URL: {avatar_url}")

    # Step 4: download
    download_image(avatar_url, output_file)

    print(f"Saved to: {output_file}")


def parse_refresh_time(time_str: str) -> int:
    """Parse time string like '1h', '30min', '1d' into seconds."""
    match = re.match(r"^(\d+)([hdms])$", time_str.lower())
    if not match:
        raise ValueError(
            f"Invalid refresh_time format: {time_str}. Use e.g. '1h', '30min', '1d', '300s'"
        )

    num, unit = match.groups()
    num = int(num)

    multipliers = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
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

    raise FileNotFoundError(
        "No config file found in current directory (config.yml or config.yaml)"
    )


def download_video(
    url: str,
    out_dir: Path,
    default_format: str,
    archive_path: Path,
    playlist_index: int,
):
    ydl_opts = {
        "format": f"bestaudio[ext={default_format}]/bestaudio/best",
        #"outtmpl": str(out_dir / f"{playlist_index:03d} - %(title)s.%(ext)s"),
        "outtmpl": str(out_dir / f"%(upload_date>%Y-%m-%d)s %(title)s.%(ext)s"),
        # Audio extraction
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
            },
            {
                "key": "FFmpegMetadata",
            },
            {
                "key": "EmbedThumbnail",
            },
        ],
        "download_archive": str(archive_path),
        # Thumbnail handling
        "writethumbnail": True,
        "convertthumbnails": "jpg",  # critical for compatibility with MP3
        # Optional but sane defaults
        "noplaylist": False,
        "ignoreerrors": True,
    }

    with YoutubeDL(ydl_opts) as ydl: # type: ignore
        ydl.download([url])


def download_playlist(entry, default_format: str, archive_path: Path):

    url = entry.get("url")

    if not url:
        raise ValueError("Each playlist entry must specify 'url'")

    out_dir = Path(entry.get("out_dir", "/audiobookshelf"))
    out_dir.mkdir(parents=True, exist_ok=True)

    # Map each playlist to a book directory to align with Audiobookshelf structure
    book_title = entry.get("book_title") or "%(playlist_title)s"
    book_dir = out_dir / book_title
    book_dir.mkdir(parents=True, exist_ok=True)
    
    info = extract_playlist_info(url)
    if not entry.get("author"):    
        author_name = info.get("uploader", "Unknown")
    else:
        author_name = entry.get("author")
    
    if not entry.get("description"):
        description = info.get("description", "")
    else:
        description = entry.get("description", "")

    metadata = {
        "title": book_title,
        "author": author_name,
        "description": description,
    }
    metadata_file = book_dir / "metadata.json"
    if not metadata_file.exists():
        metadata_file.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    cover_image = book_dir / "cover.jpg"
    if not cover_image.exists():
        try:
            download_playlist_author_avatar(url, str(cover_image))
        except Exception as e:
            print(f"Warning: Failed to download cover image: {e}")

    urls = get_playlist_urls(url)
    start = 0
    #end = min(5, len(urls))
    end = len(urls)-1
    for i, url in enumerate(urls[start:end], start=start):
        print(url)
        download_video(
            url, book_dir, default_format, archive_path, playlist_index=i + 1
        )


def get_playlist_urls(playlist_url: str):
    ydl_opts = {
        "quiet": True,
        "extract_flat": True,  # critical: avoids resolving each video fully
        "skip_download": True,  # ensures nothing is downloaded
    }

    with YoutubeDL(ydl_opts) as ydl: # type: ignore
        info = ydl.extract_info(playlist_url, download=False)

    # Validate it's actually a playlist
    if "entries" not in info:
        raise ValueError("URL is not a playlist or has no entries")

    urls = []
    for entry in info["entries"]: # type: ignore
        if entry is None:
            continue

        # 'url' is often the video ID when extract_flat=True
        if "url" in entry:
            urls.append(entry["url"])

    return urls


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="yt-abs: Youtube -> Audiobookshelf playlist downloader"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to YAML config file (default: config.yml or config.yaml)",
    )
    parser.add_argument(
        "--format", type=str, default=DEFAULT_FORMAT, help="Audio format, default m4a"
    )
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

    refresh_time_str = config.get("refresh_time")
    if refresh_time_str:
        refresh_seconds = parse_refresh_time(refresh_time_str)
        print(
            f"Starting periodic download every {refresh_time_str} ({refresh_seconds} seconds)"
        )
    else:
        refresh_seconds = None

    try:
        while True:
            for playlist in playlists:
                download_playlist(
                    playlist, default_format=args.format, archive_path=archive_path
                )

            if refresh_seconds is None:
                break

            print(f"Waiting {refresh_time_str} before next update...")
            time.sleep(refresh_seconds)
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting.")
        sys.exit(0)
