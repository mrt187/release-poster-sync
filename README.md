# release-poster-sync

Turns your Radarr/Sonarr release calendar into a browsable "Coming Soon"
library in Emby — with countdown and season/episode badges on the posters.

Tested with Emby Server v4.10.0.17 (beta).

## Setup

1. Save the following as `docker-compose.yml` in a new folder:

```yaml
services:
  release-poster-sync:
    image: ghcr.io/mrt187/release-poster-sync:latest
    container_name: release-poster-sync
    environment:
      RADARR_URL: "${RADARR_URL}"
      RADARR_API_KEY: "${RADARR_API_KEY}"
      SONARR_URL: "${SONARR_URL}"
      SONARR_API_KEY: "${SONARR_API_KEY}"
      DAYS_AHEAD: "${DAYS_AHEAD:-30}"
      CRON_SCHEDULE: "${CRON_SCHEDULE:-1 0 * * *}"
      LOG_LEVEL: "${LOG_LEVEL:-INFO}"
      TZ: "${TZ:-Europe/Berlin}"
      PUID: "${PUID:-99}"
      PGID: "${PGID:-100}"
    volumes:
      - ${POSTERS_PATH:-./posters}:/posters
    restart: unless-stopped
```

2. Put `.env.example` in the same folder, rename it to `.env`, and fill in
   your values (Radarr/Sonarr URL + API key, target folder, timezone).
3. Start (reads `.env` automatically, pulls the pre-built image from GHCR):
4. In Emby: **Add library** → content type **Mixed movies and shows** →
   select your `POSTERS_PATH` folder.
   - Under "Metadata downloaders", keep TheMovieDb **enabled** so Emby fetches
     cast, trailer, and description itself. Posters are still not overwritten
     as long as "Prefer embedded/local images" stays enabled in the library
     settings (default).

## Configuration (`.env`)

| Variable | Description |
|---|---|
| `RADARR_URL` / `RADARR_API_KEY` | Radarr connection |
| `SONARR_URL` / `SONARR_API_KEY` | Sonarr connection |
| `DAYS_AHEAD` | Calendar range in days (default 30) |
| `CRON_SCHEDULE` | Sync interval (default daily at 00:01) |
| `TZ` | Timezone for date/countdown calculations |
| `POSTERS_PATH` | Host folder for the generated posters |
| `PUID` / `PGID` | User/group ID the container runs as (default `99`/`100`, matches Unraid's `nobody:users`) |

## Security

- Runs as a non-root user, configurable via `PUID`/`PGID` (default `99`/`100`,
  matching Unraid's `nobody:users`). Set these in `.env` to match your host
  user if needed — no manual `chown` required, the container adjusts
  ownership of `/posters` on startup.
- API keys are masked before being logged.
- The `supercronic` binary is verified via SHA1 checksum.

## How it works

- Polls `/api/v3/calendar` on Radarr and Sonarr (today through `DAYS_AHEAD`
  days; already-released titles are skipped).
- Creates a folder per movie/show with a cached original poster, a rendered
  `poster.jpg` (badges recalculated on every sync, e.g. countdown),
  placeholder video, and `.nfo`.
- The `.nfo` contains `tmdbid`/`imdbid`, so Emby's TheMovieDb provider loads
  cast, trailer, and description itself.
- Removes folders no longer in the calendar range.

---

*This project was vibe coded — built through conversation with an AI, not
hand-crafted line by line. Review the code before trusting it in production.*