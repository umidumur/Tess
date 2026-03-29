#!/usr/bin/env python3
"""Yandex Music Downloader — модуль для скачивания треков."""

import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Optional, Tuple

# ====================== ИСПРАВЛЕНИЕ ПУТЕЙ ======================
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

import aiohttp
from dotenv import load_dotenv
from mutagen.id3 import ID3
from mutagen.id3._frames import APIC, TALB, TIT2, TPE1
from mutagen.mp3 import MP3
from yandex_music import ClientAsync

load_dotenv()

# Попытка импортировать telegram_log с fallback
try:
    from scripts.telegram_logger import telegram_log
except ImportError:

    async def telegram_log(message: str, level: str = "INFO", **_):
        print(f"[{level}] {message}")

    print("⚠️ telegram_log не найден, используется заглушка")

DOWNLOAD_DIR: Path = Path(os.getenv("DOWNLOAD_DIR", "downloads"))
DOWNLOAD_DIR.mkdir(exist_ok=True)

MAX_FILENAME_LENGTH = 200


class TrackCache:
    """Кэш file_id треков."""

    def __init__(self, db_file: str = "track_database.json"):
        self.db_file = Path(db_file)
        self.cache: dict = self._load()

    def _load(self) -> dict:
        try:
            with open(self.db_file, encoding="utf-8") as f:
                data = __import__("json").load(f)
                return data.get("track_cache", {}) if isinstance(data, dict) else {}
        except Exception:  # pylint: disable=broad-except
            return {}

    def _save(self) -> None:
        try:
            with open(self.db_file, "w", encoding="utf-8") as f:
                __import__("json").dump(
                    {"track_cache": self.cache}, f, indent=2, ensure_ascii=False
                )
        except Exception as e:  # pylint: disable=broad-except
            print(f"Ошибка сохранения кэша: {e}")

    def get(self, track_id: str) -> Optional[str]:
        return self.cache.get(track_id)

    def set(self, track_id: str, file_id: str) -> None:
        self.cache[track_id] = file_id
        self._save()


track_cache = TrackCache()


class YandexDownloader:
    """Упрощённый и стабильный downloader."""

    def __init__(self):
        self.ym_client: Optional[ClientAsync] = None

    async def _get_client(self) -> Optional[ClientAsync]:
        if self.ym_client is None:
            try:
                from scripts.yandex_ynison import get_yandex_client

                self.ym_client = await get_yandex_client()
            except Exception as e:  # pylint: disable=broad-except
                print(f"Не удалось получить yandex_client: {e}")
        return self.ym_client

    @staticmethod
    def _clean_filename(name: str) -> str:
        name = re.sub(r'[\\/*?:"<>|]', "", name)
        name = re.sub(r"\s+", " ", name).strip()
        return name[:MAX_FILENAME_LENGTH]

    async def download_track(self, track_id: str) -> Optional[Tuple[Path, str]]:
        """Основной метод скачивания трека."""
        try:
            client = await self._get_client()
            if not client:
                await telegram_log("Не удалось подключиться к Yandex Music", level="ERROR")
                return None

            # Получаем информацию о треке с таймаутом
            try:
                track = (await asyncio.wait_for(client.tracks([track_id]), timeout=10.0))[0]
            except asyncio.TimeoutError:
                await telegram_log(f"Таймаут при получении данных трека {track_id}", level="ERROR")
                return None
            except Exception as e:  # pylint: disable=broad-except
                await telegram_log(
                    f"Ошибка получения данных трека {track_id}: {e}", level="ERROR"
                )
                return None

            artists_str = ", ".join(a.name for a in track.artists if a.name) or "Unknown Artist"
            filename = self._clean_filename(f"{track.title} - {artists_str}.mp3")
            filepath = DOWNLOAD_DIR / filename

            await telegram_log(f"Скачиваем: {track.title} — {artists_str}", level="INFO")

            # Скачивание файла
            try:
                download_info = await asyncio.wait_for(
                    track.get_download_info_async(), timeout=15.0
                )
                if not download_info:
                    await telegram_log("Нет данных для скачивания", level="ERROR")
                    return None

                best_quality = max(download_info, key=lambda x: x.bitrate_in_kbps)
                await asyncio.wait_for(best_quality.download_async(str(filepath)), timeout=40.0)
            except asyncio.TimeoutError:
                await telegram_log("Таймаут при скачивании файла", level="ERROR")
                return None
            except Exception as e:  # pylint: disable=broad-except
                await telegram_log(f"Ошибка скачивания файла: {e}", level="ERROR")
                return None

            # Метаданные
            await self._add_metadata(filepath, track)

            caption = (
                f"🎵 **{track.title}**\n"
                f"👤 {artists_str}\n"
                f"💿 {track.albums[0].title if track.albums else 'Unknown Album'}\n"
                f"🔗 [Яндекс Музыка](https://music.yandex.ru/track/{track_id})"
            )

            await telegram_log(f"Трек успешно скачан: {filename}", level="INFO")
            return filepath, caption

        except Exception as e:  # pylint: disable=broad-except
            await telegram_log(
                f"Критическая ошибка скачивания трека {track_id}: {e}", level="ERROR"
            )
            return None

    async def _add_metadata(self, filepath: Path, track) -> None:
        """Добавляет метаданные (не критично)."""
        try:
            audio = MP3(str(filepath), ID3=ID3)
            if audio.tags is None:
                audio.add_tags()

            if audio.tags is not None:
                audio.tags.add(TIT2(encoding=3, text=track.title))
                artists = ", ".join(a.name for a in track.artists if a.name)
                audio.tags.add(TPE1(encoding=3, text=artists))

                if track.albums:
                    audio.tags.add(TALB(encoding=3, text=track.albums[0].title))

                # Обложка (не критично)
                if track.cover_uri:
                    try:
                        cover_url = f"https://{track.cover_uri.replace('%%', '1000x1000')}"
                        async with aiohttp.ClientSession(timeout=8) as session:
                            async with session.get(cover_url) as resp:
                                if resp.status == 200:
                                    cover_data = await resp.read()
                                    audio.tags.add(
                                        APIC(
                                            encoding=3,
                                            mime="image/jpeg",
                                            type=3,
                                            desc="Cover",
                                            data=cover_data,
                                        )
                                    )
                    except Exception:  # pylint: disable=broad-except
                        pass

            audio.save()
        except Exception as e:  # pylint: disable=broad-except
            await telegram_log(
                f"Не удалось добавить метаданные: {e}", level="WARNING"
            )


# Глобальный экземпляр
yandex_downloader = YandexDownloader()
