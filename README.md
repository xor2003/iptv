# Working IPTV playlist

This repository periodically fetches public M3U sources, checks each URL with
`ffprobe`, and publishes only entries where a video stream is detected.

Playlist URL:

```text
https://raw.githubusercontent.com/xor2003/iptv/main/serbia-working.m3u
```

The source list includes IPTV-org Serbian, Serbia, and selected Russian and
English channels, plus public Balkan playlists. The Russian and English feeds
use a small name-based allowlist for news, public broadcasters, science,
culture, kids, music, and documentary channels. Edit `sources.txt` to add or
remove a source. The workflow runs daily and can also be started manually.

An alive check is time-specific. A stream may be geo-blocked, temporary, or
become unavailable after the workflow publishes it. This repository stores
playlist links and metadata; it does not proxy or copy video streams.
