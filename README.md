# Working IPTV playlist

This repository periodically fetches public M3U sources, checks each URL with
`ffprobe`, and publishes only entries where a video stream is detected.

Playlist URL:

```text
https://raw.githubusercontent.com/xor2003/iptv/main/serbia-working-sr.m3u
```

Language playlists:

```text
https://raw.githubusercontent.com/xor2003/iptv/main/serbia-working-sr.m3u
https://raw.githubusercontent.com/xor2003/iptv/main/serbia-working-ru.m3u
https://raw.githubusercontent.com/xor2003/iptv/main/serbia-working-en.m3u
```

The source list includes IPTV-org Serbian, Serbia, and selected Russian and
English channels, plus public Balkan playlists. The Russian and English feeds
use a small name-based allowlist for news, public broadcasters, science,
culture, kids, music, and documentary channels; Pluto TV ad-supported entries
are excluded. Edit `sources.txt` to add or remove a source. The workflow runs
daily and can also be started manually.

The auxiliary feeds are restricted to Serbian/Balkan metadata and names.

The generated M3U headers retain EPG URLs supplied by the upstream sources.
OpenTV may detect these automatically; if it asks for a separate XMLTV source,
use the EPG URL shown by the player or assign the guide by matching `tvg-id`.
EPG coverage depends on the broadcaster and is usually better for IPTV-org
channels than for independent Balkan sources.

An alive check is time-specific. A stream may be geo-blocked, temporary, or
become unavailable after the workflow publishes it. This repository stores
playlist links and metadata; it does not proxy or copy video streams.
