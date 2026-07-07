# CLAUDE.md — release-poster-sync: Metadaten-Umbau auf Emby

## Ziel

Radarr/Sonarr liefern künftig **nur noch Kalenderdaten** (Titel, Jahr, Datum,
tmdbId/imdbId, Poster/Backdrop-URL für das Countdown-Overlay). **Cast,
Trailer und ausführliche Beschreibung soll Emby selbst über seinen
TheMovieDb-Metadatenanbieter beziehen.** Das Poster-Countdown-Overlay bleibt
unverändert erhalten.

Führe die folgenden Änderungen exakt wie beschrieben durch. Keine
zusätzlichen Refactorings, keine Änderungen an Funktionen/Variablen, die
unten nicht erwähnt sind.

---

## 1. `sync.py`

### 1.1 Entfernen (komplett löschen)

- Funktion `fetch_tmdb_trailer_id()`
- Funktion `fetch_tmdb_cast()`
- Funktion `download_trailer()`
- Funktion `fetch_radarr_cast()`
- Funktion `build_actor_tags()`
- Globale Variablen: `TMDB_API_KEY`, `DOWNLOAD_TRAILERS`, `DUMMY_VIDEO`-Nutzung
  bleibt (siehe 1.4), aber der Trailer-Download-Zweig entfällt
- `import subprocess` in `download_trailer()` entfällt automatisch mit der
  Funktion

### 1.2 `NFO_TEMPLATE` anpassen

Aktuell:

```python
NFO_TEMPLATE = """<movie>
  <title>{display_title}</title>
  <year>{year}</year>
  <premiered>{release_date}</premiered>
  <tagline>{date_tag}</tagline>
  <plot>{plot}</plot>
  <rating>{rating}</rating>
{genre_tags}  <genre>ComingSoon</genre>
{actor_tags}  <lockdata>true</lockdata>
</movie>
"""
```

Neu:

```python
NFO_TEMPLATE = """<movie>
  <title>{display_title}</title>
  <year>{year}</year>
  <premiered>{release_date}</premiered>
  <tagline>{date_tag}</tagline>
  <plot>{plot}</plot>
  <rating>{rating}</rating>
{genre_tags}  <genre>ComingSoon</genre>
{tmdb_tag}{imdb_tag}  <lockdata>false</lockdata>
</movie>
"""
```

- `{actor_tags}` Platzhalter entfällt.
- Neue Platzhalter `{tmdb_tag}` und `{imdb_tag}`, jeweils entweder
  `  <tmdbid>{id}</tmdbid>\n` bzw. `  <imdbid>{id}</imdbid>\n` oder leerer
  String, falls die ID fehlt.
- `lockdata` wird von `true` auf `false` geändert, sonst ignoriert Emby die
  IDs und scraped nicht nach.

### 1.3 Neue Hilfsfunktion

```python
def build_id_tags(tmdb_id, imdb_id) -> tuple:
    """Gibt (tmdb_tag, imdb_tag) als NFO-Zeilen zurück, leer falls ID fehlt."""
    tmdb_tag = f"  <tmdbid>{tmdb_id}</tmdbid>\n" if tmdb_id else ""
    imdb_tag = f"  <imdbid>{saxutils.escape(str(imdb_id))}</imdbid>\n" if imdb_id else ""
    return tmdb_tag, imdb_tag
```

### 1.4 `create_entry()` anpassen

- Parameter `actors=None, youtube_trailer_id=""` entfernen.
- Neue Parameter: `tmdb_id=None, imdb_id=None`.
- Trailer-Video-Block:

  Aktuell:
  ```python
  video_path = os.path.join(entry_dir, f"{folder_name}.mp4")
  if not os.path.exists(video_path):
      trailer_downloaded = False
      if DOWNLOAD_TRAILERS and youtube_trailer_id:
          trailer_downloaded = download_trailer(youtube_trailer_id, video_path)
      if not trailer_downloaded:
          shutil.copyfile(DUMMY_VIDEO, video_path)
  ```

  Neu (nur noch Platzhalter-Video, kein Trailer-Download mehr):
  ```python
  video_path = os.path.join(entry_dir, f"{folder_name}.mp4")
  if not os.path.exists(video_path):
      shutil.copyfile(DUMMY_VIDEO, video_path)
  ```

- `.nfo`-Erstellung: `actor_tags` durch `tmdb_tag`/`imdb_tag`
  (aus `build_id_tags(tmdb_id, imdb_id)`) ersetzen, im `NFO_TEMPLATE.format()`
  entsprechend übergeben statt `actor_tags=actor_tags`.

### 1.5 `sync_radarr()` anpassen

- Zeile mit `actors = fetch_radarr_cast(...)` entfernen.
- Zeile mit `youtube_trailer_id = movie.get("youTubeTrailerId", "")`
  entfernen.
- Neu hinzufügen: `tmdb_id = movie.get("tmdbId")` und
  `imdb_id = movie.get("imdbId")`.
- Aufruf von `create_entry(...)` anpassen: `actors=actors,
  youtube_trailer_id=youtube_trailer_id` ersetzen durch
  `tmdb_id=tmdb_id, imdb_id=imdb_id`.

### 1.6 `sync_sonarr()` anpassen

- Block entfernen:
  ```python
  tmdb_id = series.get("tmdbId")
  youtube_trailer_id = ""
  actors = []
  if DOWNLOAD_TRAILERS and tmdb_id:
      youtube_trailer_id = fetch_tmdb_trailer_id(tmdb_id, "tv")
  if TMDB_API_KEY and tmdb_id:
      actors = fetch_tmdb_cast(tmdb_id, "tv")
  ```
- Ersetzen durch:
  ```python
  tmdb_id = series.get("tmdbId")
  imdb_id = series.get("imdbId")
  ```
- Aufruf von `create_entry(...)` anpassen: `actors=actors,
  youtube_trailer_id=youtube_trailer_id` ersetzen durch
  `tmdb_id=tmdb_id, imdb_id=imdb_id`.

### 1.7 Was unverändert bleibt

- `render_poster()`, `draw_pill()`, Countdown-/Badge-Logik: **keine
  Änderung**.
- `DUMMY_VIDEO`, `download()`, `extract_image_url()`, `safe_filename()`,
  `is_released()`, `countdown_text()`, `build_plot()`, `build_date_tag()`,
  `build_genre_tags()`, `extract_rating()`, `mask_key()`, `cleanup()`,
  `main()`: **keine Änderung**.

---

## 2. `Dockerfile`

- Zeile `&& pip install --no-cache-dir yt-dlp` entfernen (kein
  Trailer-Download mehr nötig).
- `ffmpeg` in der `apt-get install`-Zeile **behalten** (wird weiterhin für
  die Erzeugung von `dummy.mp4` gebraucht).

---

## 3. `docker-compose.yml`

Folgende Environment-Variablen entfernen:

```yaml
      DOWNLOAD_TRAILERS: "${DOWNLOAD_TRAILERS:-false}"
      TMDB_API_KEY: "${TMDB_API_KEY:-}"
```

Alle anderen Variablen bleiben unverändert.

**Parallelbetrieb zum Original:** `container_name` (aktuell
`release-poster-sync`) sowie der `image`-Name/Tag umbenennen (z. B.
`release-poster-sync-test`), damit kein Konflikt mit dem
Original-Container entsteht.

---

## 4. `README.md`

- Compose-Beispiel im Setup-Abschnitt: gleiche zwei Zeilen wie in Punkt 3
  entfernen.
- Tabelle "Configuration (`.env`)": Zeilen für `DOWNLOAD_TRAILERS` und
  `TMDB_API_KEY` entfernen.
- Setup-Schritt 4 ("Under 'Metadata downloaders', uncheck all providers..."):
  **umkehren** — Hinweis, dass TheMovieDb als Metadaten-Anbieter für die
  Bibliothek **aktiviert** bleiben soll (nicht deaktivieren), damit Emby
  Cast, Trailer und Beschreibung selbst nachlädt. Poster werden trotzdem
  nicht überschrieben, solange "Lokale Bilder bevorzugen" in den
  Bibliothekseinstellungen aktiv ist (Standard).
- Abschnitt "How it works": Erwähnung von Cast/Trailer-Abruf entfernen,
  stattdessen ergänzen, dass `.nfo` `tmdbid`/`imdbid` enthält und Emby damit
  Cast, Trailer und Beschreibung selbst lädt.

---

## 5. `requirements.txt`

Keine Änderung (`requests`, `Pillow` weiterhin benötigt).

---

## 6. CHANGELOG.md

Neue Datei `CHANGELOG.md` im Projektroot anlegen. Nur wesentliche
Änderungen stichpunktartig, **keine Code-Details**, z. B.:

- Cast/Trailer/Beschreibung werden nicht mehr über TMDb/Radarr geladen,
  sondern von Emby selbst bezogen (`tmdbid`/`imdbid` im `.nfo`)
- Trailer-Download (yt-dlp) entfernt
- `TMDB_API_KEY` und `DOWNLOAD_TRAILERS` nicht mehr nötig
- Poster-Countdown-Overlay unverändert

## 7. Testing / Akzeptanzkriterien

1. Container baut ohne Fehler (kein `yt-dlp` mehr installiert).
2. `docker compose up` ohne `TMDB_API_KEY`/`DOWNLOAD_TRAILERS` im `.env`
   funktioniert fehlerfrei.
3. Nach einem Sync-Lauf enthält jede erzeugte `.nfo`-Datei `<tmdbid>` (bzw.
   `<imdbid>` falls keine tmdbId vorhanden) und `<lockdata>false</lockdata>`.
4. Keine `<actor>`-Tags mehr in den `.nfo`-Dateien.
5. Poster-Countdown-Overlay (`poster.jpg`) wird weiterhin korrekt gerendert.
6. Emby scraped nach Aktivierung des TheMovieDb-Providers automatisch Cast,
   Trailer und Beschreibung für die Bibliothek nach.