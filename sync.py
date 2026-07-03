#!/usr/bin/env python3
"""Lädt kommende Radarr/Sonarr-Releases und legt pro Titel einen Ordner mit
Poster, Platzhalter-Video und .nfo an (Emby-Bibliothek "Gemischter Inhalt")."""

import os
import re
import shutil
import logging
from datetime import datetime, timedelta

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
  <plot>Demnächst verfügbar ({release_date})</plot>
  <lockdata>true</lockdata>
</movie>
"""


def mask_key(url: str) -> str:
    """Entfernt den apikey-Wert aus einer URL, bevor sie geloggt wird."""
    return re.sub(r"(apikey=)[^&]+", r"\1***", url)


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


def format_date(iso_date: str) -> str:
    try:
        return datetime.strptime(iso_date[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        return ""


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


def extract_poster_url(images, base_url: str, api_key: str):
    for img in images or []:
        if img.get("coverType") != "poster":
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


def create_entry(folder_name: str, title: str, year, poster_url: str, release_date: str, episode_badge: str = None):
    """Legt Ordner mit Poster, Platzhalter-Video und .nfo an; Poster-Overlay wird bei jedem Lauf neu gerendert."""
    entry_dir = os.path.join(OUTPUT_DIR, folder_name)
    os.makedirs(entry_dir, exist_ok=True)

    original_path = os.path.join(entry_dir, ".poster_original.jpg")
    poster_path = os.path.join(entry_dir, "poster.jpg")

    if not os.path.exists(original_path) and poster_url:
        download(poster_url, original_path)

    if os.path.exists(original_path):
        render_poster(original_path, poster_path, release_date, episode_badge)

    video_path = os.path.join(entry_dir, f"{folder_name}.mp4")
    if not os.path.exists(video_path):
        shutil.copyfile(DUMMY_VIDEO, video_path)

    nfo_path = os.path.join(entry_dir, "movie.nfo")
    if not os.path.exists(nfo_path):
        with open(nfo_path, "w", encoding="utf-8") as f:
            f.write(NFO_TEMPLATE.format(display_title=title, year=year or "", release_date=release_date))

    log.info("Eintrag aktualisiert: %s", folder_name)


def sync_radarr() -> set:
    expected = set()
    if not RADARR_URL or not RADARR_API_KEY:
        log.info("Radarr nicht konfiguriert, überspringe.")
        return expected

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
        return expected

    log.info("Radarr: %d anstehende Filme gefunden.", len(movies))

    for movie in movies:
        title = movie.get("title", "Unbekannt")
        year = movie.get("year", "")
        release_date = movie.get("digitalRelease") or movie.get("physicalRelease") or movie.get("inCinemas") or ""
        if is_released(release_date):
            continue
        folder_name = safe_filename(f"{title} ({year})") if year else safe_filename(title)

        poster_url = extract_poster_url(movie.get("images"), RADARR_URL, RADARR_API_KEY)
        create_entry(folder_name, title, year, poster_url, release_date[:10])
        expected.add(folder_name)

    return expected


def sync_sonarr() -> set:
    expected = set()
    if not SONARR_URL or not SONARR_API_KEY:
        log.info("Sonarr nicht konfiguriert, überspringe.")
        return expected

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
        return expected

    seen_series = set()
    log.info("Sonarr: %d anstehende Episoden gefunden.", len(episodes))

    for ep in episodes:
        series = ep.get("series") or {}
        series_id = series.get("id")
        title = series.get("title", "Unbekannt")
        year = series.get("year", "")
        air_date = ep.get("airDate", "")
        if is_released(air_date):
            continue

        if series_id in seen_series:
            continue
        seen_series.add(series_id)

        folder_name = safe_filename(f"{title} ({year})") if year else safe_filename(title)
        poster_url = extract_poster_url(series.get("images"), SONARR_URL, SONARR_API_KEY)
        season_num = ep.get("seasonNumber")
        episode_num = ep.get("episodeNumber")
        episode_badge = None
        if season_num is not None and episode_num is not None:
            episode_badge = f"S{season_num:02d}E{episode_num:02d}"

        create_entry(folder_name, title, year, poster_url, air_date, episode_badge)
        expected.add(folder_name)

    return expected


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
    expected |= sync_radarr()
    expected |= sync_sonarr()
    cleanup(expected)
    log.info("Sync abgeschlossen.")


if __name__ == "__main__":
    main()
