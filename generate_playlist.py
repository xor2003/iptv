#!/usr/bin/env python3
"""Fetch M3U sources, keep entries with a detected video stream, and emit M3U."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True)
class Entry:
    source: str
    info: str
    url: str
    user_agent: str = ""
    referrer: str = ""


INTERESTING = {
    "ru": re.compile(r"(?i)(первый канал|россия.?1|россия.?24|россия.?к|культура|нтв|рен.?тв|rt russian|ртви|rbc|рбк|мир|пятый канал|звезда|матч|тнт|стс|пятница|муз.?тв|карусель|москва.?24|спас|победа|наука|планета|познавательное|дождь|москва|петербург)"),
    "en": re.compile(r"(?i)(bbc|cnn|sky news|al.?jazeera|euronews|france 24|dw|deutsche welle|bloomberg|cnbc|reuters|nhk world|cgtn|trt world|wion|abc news|nasa|weather|national geographic|discovery|history|smithsonian|animal planet|documentary|ted|science|nature|pluto|plex|rakuten|red bull|motorsport|espn|world news|voa|newsmax|rt english)"),
}
SERBIA = re.compile(r'(?i)(tvg-id="[^"]*\.rs|tvg-country="RS"|tvg-language="Serbian"|group-title="Serbia"|\b(rts|kurir|pannon|dmsat|dm sat|pink|prva|happy|nova s|narodna|red tv|arena sport|arena fight|rtv novi pazar|rtv bap)\b)')


def read_sources(path: Path) -> list[tuple[str, str, str]]:
    result = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            fields = line.split("|", 2)
            label, url = fields[:2]
            selector = fields[2].strip() if len(fields) == 3 else ""
        except ValueError as exc:
            raise ValueError(f"Invalid source line: {line!r}") from exc
        result.append((label.strip(), url.strip(), selector))
    if not result:
        raise ValueError(f"No sources found in {path}")
    return result


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "iptv-playlist-generator/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def parse_m3u(source: str, text: str, selector: str = "") -> list[Entry]:
    lines = text.splitlines()
    entries: list[Entry] = []
    pending_info = None
    user_agent = ""
    referrer = ""
    for line in lines:
        line = line.strip()
        if line.startswith("#EXTINF:"):
            pending_info = line
            user_agent = ""
            referrer = ""
        elif line.lower().startswith("#extvlcopt:http-user-agent:"):
            user_agent = line.split(":", 2)[2]
        elif line.lower().startswith("#extvlcopt:http-referrer:"):
            referrer = line.split(":", 2)[2]
        elif pending_info and line and not line.startswith("#"):
            if line.startswith(("http://", "https://", "rtmp://", "rtsp://")):
                if not selector or (
                    selector.startswith("interesting-") and INTERESTING[selector[-2:]].search(pending_info)
                ) or (selector == "serbia" and SERBIA.search(pending_info)):
                    entries.append(Entry(source, pending_info, line, user_agent, referrer))
            pending_info = None
    return entries


def channel_key(entry: Entry) -> str:
    match = re.search(r'(?i)(?:tvg-id|tvg-name)="([^"]+)"', entry.info)
    if match:
        return match.group(1).strip().lower()
    return entry.info.split(",", 1)[-1].strip().lower()


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))


def probe(entry: Entry, timeout: int, retries: int) -> tuple[Entry, str]:
    command = [
        "ffprobe", "-v", "error", "-rw_timeout", str(timeout * 1_000_000),
        "-probesize", "1000000", "-analyzeduration", "3000000",
        "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height",
        "-of", "csv=p=0", "-read_intervals", "%+5",
    ]
    if entry.user_agent:
        command += ["-user_agent", entry.user_agent]
    if entry.referrer:
        command += ["-headers", f"Referer: {entry.referrer}\r\n"]
    command.append(entry.url)
    last_error = "probe failed"
    for attempt in range(retries + 1):
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout + 4)
            video = completed.stdout.strip().splitlines()
            if completed.returncode == 0 and video:
                return entry, video[0]
            last_error = completed.stderr.strip().splitlines()[-1] if completed.stderr.strip() else last_error
        except (OSError, subprocess.TimeoutExpired) as exc:
            last_error = type(exc).__name__
        if attempt < retries:
            time.sleep(1)
    return entry, ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", type=Path, default=Path("sources.txt"))
    parser.add_argument("--output", type=Path, default=Path("serbia-working.m3u"))
    parser.add_argument("--status", type=Path, default=Path("status.json"))
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--retries", type=int, default=1)
    args = parser.parse_args()

    if not shutil.which("ffprobe"):
        print("ffprobe is required", file=sys.stderr)
        return 2

    sources = read_sources(args.sources)
    all_entries: list[Entry] = []
    source_status = []
    for label, url, selector in sources:
        try:
            entries = parse_m3u(label, fetch(url), selector)
            all_entries.extend(entries)
            source_status.append({"label": label, "url": url, "entries": len(entries), "error": ""})
            print(f"{label}: {len(entries)} entries", file=sys.stderr)
        except Exception as exc:
            source_status.append({"label": label, "url": url, "entries": 0, "error": str(exc)})
            print(f"{label}: {exc}", file=sys.stderr)

    unique: dict[str, Entry] = {}
    for entry in all_entries:
        unique.setdefault(canonical_url(entry.url), entry)

    working: list[tuple[Entry, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(probe, entry, args.timeout, args.retries) for entry in unique.values()]
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            entry, video = future.result()
            if video:
                working.append((entry, video))
            if index % 50 == 0 or index == len(futures):
                print(f"probed {index}/{len(futures)}; working={len(working)}", file=sys.stderr)

    # Prefer the first working URL for a channel, following sources.txt order.
    source_order = {label: index for index, (label, _, _) in enumerate(sources)}
    working.sort(key=lambda pair: source_order.get(pair[0].source, 9999))
    selected: list[tuple[Entry, str]] = []
    channel_seen: set[str] = set()
    for entry, video in working:
        key = channel_key(entry)
        if key not in channel_seen:
            selected.append((entry, video))
            channel_seen.add(key)

    output = ["#EXTM3U"]
    for entry, _video in selected:
        output.append(entry.info)
        if entry.user_agent:
            output.append(f"#EXTVLCOPT:http-user-agent={entry.user_agent}")
        if entry.referrer:
            output.append(f"#EXTVLCOPT:http-referrer={entry.referrer}")
        output.append(entry.url)
    args.output.write_text("\n".join(output) + "\n", encoding="utf-8")
    args.status.write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_entries": len(all_entries),
        "unique_urls_probed": len(unique),
        "working_urls": len(working),
        "published_channels": len(selected),
        "sources": source_status,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"published {len(selected)} channels to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
