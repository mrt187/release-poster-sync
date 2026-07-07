# Changelog

## Unreleased

- Emby lädt Cast, Trailer und Beschreibung jetzt selbst über seinen TheMovieDb-Metadatenanbieter statt über Radarr/Sonarr.
- Trailer-Download entfällt komplett (kein `yt-dlp` mehr im Image).
- `.nfo`-Dateien enthalten jetzt `tmdbid`/`imdbid` statt `<actor>`-Tags, `lockdata` steht auf `false`.
- Konfiguration vereinfacht: `DOWNLOAD_TRAILERS` und `TMDB_API_KEY` entfallen.
