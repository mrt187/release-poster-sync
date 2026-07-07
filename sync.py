#!/usr/bin/env python3
"""Lädt kommende Radarr/Sonarr-Releases und legt pro Titel einen Ordner mit
Poster, Platzhalter-Video und .nfo an (Emby-Bibliothek "Gemischter Inhalt")."""

import os
import re
import shutil
import logging
from datetime import datetime, timedelta, timezone

import xml.sax.saxutils as saxutils
import requests
from PIL import Image, ImageDraw, ImageFont

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("release-poster-sync")

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/posters")
DAYS_AHEAD = int(os.environ.get("DAYS_AHEAD", "30"))
DUMMY_VIDEO = "/app/dummy.mp4"
REQUEST_TIMEOUT = 30

RADARR_URL = os.environ.get("RADARR_URL", "").rstrip("/")
RADARR_API_KEY = os.environ.get("RADARR_API_KEY", "")

SONARR_URL = os.environ.get("SONARR_URL", "").rstrip("/")
SONARR_API_KEY = os.environ.get("SONARR_API_KEY", "")

SESSION = requests.Session()

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


def mask_key(url: str) -> str:
    """Entfernt api_key/apikey-Werte aus einer URL, bevor sie geloggt wird."""
    return re.sub(r"(api_?key=)[^&]+", r"\1***", url)


def build_plot(overview: str) -> str:
    return saxutils.escape((overview or "").strip()) or "Demnächst verfügbar."


def build_date_tag(release_date: str) -> str:
    try:
        d = datetime.strptime(release_date[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
        return saxutils.escape(f"Ab {d}")
    except (ValueError, TypeError):
        return "Demnächst verfügbar"


def extract_rating(ratings: dict) -> float:
    if not ratings:
        return 0.0
    for key in ("imdb", "tmdb", "value"):
        entry = ratings.get(key)
        if isinstance(entry, dict) and entry.get("value"):
            return round(float(entry["value"]), 1)
        if key == "value" and isinstance(entry, (int, float)):
            return round(float(entry), 1)
    return 0.0


def build_genre_tags(genres) -> str:
    lines = "".join(f"  <genre>{saxutils.escape(g)}</genre>\n" for g in (genres or []) if g)
    return lines


def build_id_tags(tmdb_id, imdb_id) -> tuple:
    """Gibt (tmdb_tag, imdb_tag) als NFO-Zeilen zurück, leer falls ID fehlt."""
    tmdb_tag = f"  <tmdbid>{tmdb_id}</tmdbid>\n" if tmdb_id else ""
    imdb_tag = f"  <imdbid>{saxutils.escape(str(imdb_id))}</imdbid>\n" if imdb_id else ""
    return tmdb_tag, imdb_tag


def countdown_text(release_date: str):
    try:
        rd = datetime.strptime(release_date[:10], "%Y-%m-%d").date()
        delta = (rd - datetime.now().date()).days
        if delta > 1:
            return f"{delta} Days"
        if delta == 1:
            return "Tomorrow"
        return None
    except (ValueError, TypeError):
        return None


def is_released(release_date: str) -> bool:
    try:
        rd = datetime.strptime(release_date[:10], "%Y-%m-%d").date()
        return rd <= datetime.now().date()
    except (ValueError, TypeError):
        return False


def safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "", name)
    return name.strip()


def download(url: str, dest_path: str) -> bool:
    try:
        r = SESSION.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            f.write(r.content)
        return True
    except requests.RequestException as e:
        log.warning("Download fehlgeschlagen (%s): %s", mask_key(url), mask_key(str(e)))
        return False


def extract_image_url(images, cover_type: str, base_url: str, api_key: str):
    for img in images or []:
        if img.get("coverType") != cover_type:
            continue
        rel_url = img.get("url")
        if rel_url:
            sep = "&" if "?" in rel_url else "?"
            return f"{base_url}{rel_url}{sep}apikey={api_key}"
        remote = img.get("remoteUrl")
        if remote:
            return remote
    return None


EMBY_GREEN = (82, 181, 75, 235)
RED = (200, 30, 30, 235)


def draw_pill(draw, text, font, x, y, fill, align="left", canvas_width=0):
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = int(font.size * 0.7), int(font.size * 0.45)
    box_w, box_h = text_w + pad_x * 2, text_h + pad_y * 2

    if align == "right":
        x = canvas_width - x - box_w

    box = (x, y, x + box_w, y + box_h)
    draw.rounded_rectangle(box, radius=box_h // 2, fill=fill)
    draw.text((x + pad_x - bbox[0], y + pad_y - bbox[1]), text, font=font, fill=(255, 255, 255, 255))
    return box_w, box_h


def render_poster(src_path: str, dest_path: str, release_date: str, episode_badge: str = None):
    """UPCOMING oben links, Countdown unten rechts, optionales S/E-Badge unter UPCOMING."""
    try:
        img = Image.open(src_path).convert("RGBA")
        w, h = img.size
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        font_size = max(14, int(w * 0.06))
        big_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        se_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", int(font_size * 1.1))

        margin = int(w * 0.04)

        _, upcoming_h = draw_pill(draw, "UPCOMING", big_font, margin, margin, EMBY_GREEN)

        cd = countdown_text(release_date)
        if cd:
            bbox = draw.textbbox((0, 0), cd, font=big_font)
            pad_x, pad_y = int(big_font.size * 0.7), int(big_font.size * 0.45)
            box_h = (bbox[3] - bbox[1]) + pad_y * 2
            draw_pill(draw, cd, big_font, margin, h - margin - box_h, RED, align="right", canvas_width=w)

        if episode_badge:
            draw_pill(draw, episode_badge, se_font, margin, margin + upcoming_h + int(margin * 0.4), EMBY_GREEN)

        combined = Image.alpha_composite(img, overlay).convert("RGB")
        combined.save(dest_path, "JPEG", quality=90)
    except Exception as e:
        log.warning("Poster-Overlay fehlgeschlagen (%s): %s", src_path, e)


def create_entry(folder_name: str, title: str, year, poster_url: str, backdrop_url: str,
                  overview: str, genres, rating: float, release_date: str,
                  episode_badge: str = None, tmdb_id=None, imdb_id=None):
    """Legt Ordner mit Poster, Backdrop, Platzhalter-Video und .nfo an; Poster-Overlay wird bei jedem Lauf neu gerendert."""
    entry_dir = os.path.join(OUTPUT_DIR, folder_name)
    os.makedirs(entry_dir, exist_ok=True)

    original_path = os.path.join(entry_dir, ".poster_original.jpg")
    poster_path = os.path.join(entry_dir, "poster.jpg")

    if not os.path.exists(original_path) and poster_url:
        download(poster_url, original_path)

    if os.path.exists(original_path):
        render_poster(original_path, poster_path, release_date, episode_badge)

    backdrop_path = os.path.join(entry_dir, "backdrop.jpg")
    if not os.path.exists(backdrop_path) and backdrop_url:
        download(backdrop_url, backdrop_path)

    video_path = os.path.join(entry_dir, f"{folder_name}.mp4")
    if not os.path.exists(video_path):
        shutil.copyfile(DUMMY_VIDEO, video_path)

    nfo_path = os.path.join(entry_dir, "movie.nfo")
    plot = build_plot(overview)
    genre_tags = build_genre_tags(genres)
    date_tag = build_date_tag(release_date)
    tmdb_tag, imdb_tag = build_id_tags(tmdb_id, imdb_id)
    with open(nfo_path, "w", encoding="utf-8") as f:
        f.write(NFO_TEMPLATE.format(
            display_title=saxutils.escape(title or ""),
            year=saxutils.escape(str(year or "")),
            release_date=saxutils.escape(release_date),
            plot=plot, rating=rating, genre_tags=genre_tags, date_tag=date_tag,
            tmdb_tag=tmdb_tag, imdb_tag=imdb_tag,
        ))

    log.info("Eintrag aktualisiert: %s", folder_name)


def sync_radarr():
    expected = set()
    if not RADARR_URL or not RADARR_API_KEY:
        log.info("Radarr nicht konfiguriert, überspringe.")
        return expected, True

    start = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=DAYS_AHEAD)).strftime("%Y-%m-%d")

    url = f"{RADARR_URL}/api/v3/calendar"
    params = {
        "apikey": RADARR_API_KEY,
        "start": start,
        "end": end,
        "unmonitored": "true",
    }

    try:
        r = SESSION.get(url, params=params, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        movies = r.json()
    except requests.RequestException as e:
        log.error("Radarr-Kalender konnte nicht geladen werden: %s", mask_key(str(e)))
        return expected, False

    log.info("Radarr: %d anstehende Filme gefunden.", len(movies))

    for movie in movies:
        title = movie.get("title", "Unbekannt")
        year = movie.get("year", "")
        overview = movie.get("overview", "")
        genres = movie.get("genres", [])
        rating = extract_rating(movie.get("ratings"))
        release_date = movie.get("digitalRelease") or movie.get("physicalRelease") or movie.get("inCinemas") or ""
        if is_released(release_date):
            continue
        folder_name = safe_filename(f"{title} ({year})") if year else safe_filename(title)

        images = movie.get("images")
        poster_url = extract_image_url(images, "poster", RADARR_URL, RADARR_API_KEY)
        backdrop_url = extract_image_url(images, "fanart", RADARR_URL, RADARR_API_KEY)
        tmdb_id = movie.get("tmdbId")
        imdb_id = movie.get("imdbId")
        create_entry(folder_name, title, year, poster_url, backdrop_url, overview, genres, rating,
                     release_date[:10], tmdb_id=tmdb_id, imdb_id=imdb_id)
        expected.add(folder_name)

    return expected, True


def sync_sonarr():
    expected = set()
    if not SONARR_URL or not SONARR_API_KEY:
        log.info("Sonarr nicht konfiguriert, überspringe.")
        return expected, True

    start = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=DAYS_AHEAD)).strftime("%Y-%m-%d")

    url = f"{SONARR_URL}/api/v3/calendar"
    params = {
        "apikey": SONARR_API_KEY,
        "start": start,
        "end": end,
        "unmonitored": "true",
        "includeSeries": "true",
    }

    try:
        r = SESSION.get(url, params=params, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        episodes = r.json()
    except requests.RequestException as e:
        log.error("Sonarr-Kalender konnte nicht geladen werden: %s", mask_key(str(e)))
        return expected, False

    seen_series = set()
    log.info("Sonarr: %d anstehende Episoden gefunden.", len(episodes))

    for ep in episodes:
        series = ep.get("series") or {}
        series_id = series.get("id")
        title = series.get("title", "Unbekannt")
        year = series.get("year", "")
        overview = series.get("overview", "")
        genres = series.get("genres", [])
        rating = extract_rating(series.get("ratings"))
        air_date_utc = ep.get("airDateUtc", "")
        air_date = ep.get("airDate", "")
        if air_date_utc:
            try:
                utc_dt = datetime.strptime(air_date_utc[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                air_date = utc_dt.astimezone().strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass

        if is_released(air_date):
            continue

        if series_id in seen_series:
            continue
        seen_series.add(series_id)

        season_num = ep.get("seasonNumber")
        episode_num = ep.get("episodeNumber")
        episode_badge = None
        if season_num is not None and episode_num is not None:
            episode_badge = f"S{season_num:02d}E{episode_num:02d}"

        folder_name = safe_filename(f"{title} ({year})") if year else safe_filename(title)
        images = series.get("images")
        poster_url = extract_image_url(images, "poster", SONARR_URL, SONARR_API_KEY)
        backdrop_url = extract_image_url(images, "fanart", SONARR_URL, SONARR_API_KEY)

        tmdb_id = series.get("tmdbId")
        imdb_id = series.get("imdbId")

        create_entry(folder_name, title, year, poster_url, backdrop_url, overview, genres, rating,
                     air_date, episode_badge, tmdb_id=tmdb_id, imdb_id=imdb_id)
        expected.add(folder_name)

    return expected, True


def cleanup(expected_dirs: set):
    removed = 0
    for name in os.listdir(OUTPUT_DIR):
        path = os.path.join(OUTPUT_DIR, name)
        if os.path.isdir(path) and name not in expected_dirs:
            shutil.rmtree(path)
            removed += 1
            log.info("Veralteter Eintrag entfernt: %s", name)
    log.info("Cleanup abgeschlossen, %d Eintrag/Einträge entfernt.", removed)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    log.info("Starte Sync (Zeitraum: heute + %d Tage, Ziel: %s)", DAYS_AHEAD, OUTPUT_DIR)
    expected = set()

    radarr_expected, radarr_ok = sync_radarr()
    sonarr_expected, sonarr_ok = sync_sonarr()
    expected |= radarr_expected
    expected |= sonarr_expected

    if radarr_ok and sonarr_ok:
        cleanup(expected)
    else:
        log.warning(
            "Cleanup übersprungen: mindestens ein Abruf ist fehlgeschlagen "
            "(Radarr ok=%s, Sonarr ok=%s).",
            radarr_ok, sonarr_ok,
        )

    log.info("Sync abgeschlossen.")


if __name__ == "__main__":
    main()