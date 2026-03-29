#!/usr/bin/env python3
"""Yandex Music Bio Sync — только обновление био в Telegram.

Использует общий Ynison клиент из yandex_ynison.py
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon.errors import FloodWaitError
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import InputUserSelf

# ====================== ИСПРАВЛЕНИЕ ПУТЕЙ ======================
# Добавляем корень проекта в sys.path — работает при любом способе запуска
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

load_dotenv()

from typing import Optional

from scripts.session_manager import get_client
from scripts.telegram_logger import telegram_log
from scripts.yandex_ynison import get_current_track_info

# ====================== КОНСТАНТЫ ======================
YM_THREAD: int = int(os.getenv("YM_THREAD", "0"))
BIO_THREAD: int = int(os.getenv("BIO_THREAD", "0"))
INITIAL_BIO: str = os.getenv("INITIAL_BIO", "")
KEY: str = "🎶"
LIMIT: int = 138

BIOS = [
    KEY + " Now Playing: {title} by {artists}",
    KEY + " : {title} by {artists}",
    KEY + " Now Playing: {title}",
    KEY + " : {title}",
]

logger = logging.getLogger(__name__)

client_tg = None
last_track_id: Optional[str] = None


async def update_bio():
    """Обновляет био в Telegram."""
    global last_track_id

    try:
        track_info = await get_current_track_info()
        if not track_info:
            logger.debug("Нет информации о текущем треке")
            return

        full_user = await client_tg(GetFullUserRequest(InputUserSelf()))  # type: ignore
        current_bio: str = full_user.full_user.about or ""

        is_bot_managed = KEY in current_bio

        if track_info.get("is_playing"):
            current_track_id = track_info["track_id"]

            if current_track_id != last_track_id:
                title = track_info["title"]
                artists = track_info["artists"]

                new_bio = next(
                    (
                        fmt.format(title=title, artists=artists)
                        for fmt in BIOS
                        if len(fmt.format(title=title, artists=artists)) <= LIMIT
                    ),
                    "",
                )

                if new_bio:
                    await client_tg(UpdateProfileRequest(about=new_bio))  # type: ignore
                    last_track_id = current_track_id
                    await telegram_log(f"Bio updated: {new_bio}", topic_id=BIO_THREAD, level="INFO")
                else:
                    logger.warning("Не удалось сформировать био в пределах лимита")
        else:
            last_track_id = None
            if is_bot_managed:
                # Здесь можно добавить восстановление исходного био
                pass

    except FloodWaitError as e:
        logger.warning("FloodWaitError: %d секунд", e.seconds)
        await asyncio.sleep(e.seconds)
    except Exception as e:  # pylint: disable=broad-except
        logger.error("Ошибка обновления био", exc_info=True)
        await telegram_log(f"Bio update error: {e}", topic_id=YM_THREAD, level="ERROR")


async def main():
    """Главная функция скрипта."""
    global client_tg

    print("[*] Yandex Bio Sync запущен...")

    try:
        client_tg = get_client()
        await client_tg.connect()  # type: ignore
        await telegram_log("Yandex Bio Sync успешно запущен", topic_id=YM_THREAD, level="INFO")
    except Exception as e:  # pylint: disable=broad-except
        await telegram_log(
            f"Не удалось запустить Yandex Bio Sync: {e}", level="ERROR"
        )
        print(f"❌ Ошибка запуска: {e}")
        return

    while True:
        try:
            await update_bio()
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            break
        except Exception:  # pylint: disable=broad-except
            logger.error("Неожиданная ошибка в основном цикле", exc_info=True)
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
