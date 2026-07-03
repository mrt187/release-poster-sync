# release-poster-sync

Turns your Radarr/Sonarr release calendar into a browsable "Coming Soon"
library in Emby — with countdown and season/episode badges on the posters.

Tested with Emby Server v4.10.0.17 (beta).



## Setup

1. Copy `.env.example` to `.env` and fill in your values (Radarr/Sonarr URL +
   API key, target folder, timezone). **Never commit `.env`.**
2. Start (pulls the pre-built image from GHCR):
   ```
   docker compose up -d
   ```
3. In Emby: **Add library** → content type **Mixed movies and shows** →
   select your `POSTERS_PATH` folder.
   - Under "Metadata downloaders", uncheck all providers (e.g. TheMovieDb) so
     Emby only uses the local `.nfo` files already provided.

## Configuration (`.env`)

| Variable | Description |
|---|---|
| `RADARR_URL` / `RADARR_API_KEY` | Radarr connection |
| `SONARR_URL` / `SONARR_API_KEY` | Sonarr connection |
| `DAYS_AHEAD` | Calendar range in days (default 30) |
| `CRON_SCHEDULE` | Sync interval (default every 6h) |
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
- Removes folders no longer in the calendar range.