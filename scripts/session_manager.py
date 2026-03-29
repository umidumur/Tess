#!/usr/bin/env python3
"""Session manager — одна общая сессия для всех скриптов.

Авторизация происходит ТОЛЬКО ОДИН РАЗ.
Все subprocess (yandex_sync, magic_heart и т.д.) используют ту же самую сессию.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv()

# ====================== КОНСТАНТЫ ======================
SESSION_NAME: str = os.getenv("SESSION_NAME", "Tess2")  # можно переопределить в .env

# Папка для хранения сессий (рекомендую создать)
SESSIONS_DIR: Path = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)

SESSION_PATH: str = str(SESSIONS_DIR / f"{SESSION_NAME}.session")


def get_client() -> TelegramClient:
    """Возвращает TelegramClient с одной общей сессией.

    Авторизация происходит только при первом запуске (в главном боте).
    Все остальные скрипты (subprocess) просто подключаются к уже готовой сессии.
    """
    api_id = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")

    if not api_id or not api_hash:
        raise RuntimeError("API_ID и API_HASH должны быть заданы в .env")

    client = TelegramClient(
        SESSION_PATH,  # один и тот же файл для всех
        int(api_id),
        api_hash,
        # Параметры, которые сильно помогают при работе из subprocess
        connection_retries=10,
        retry_delay=1,
        request_retries=5,
        flood_sleep_threshold=120,
        auto_reconnect=True,
    )

    return client


# ====================== УТИЛИТЫ (вызывай один раз) ======================
def clear_session() -> None:
    """Удаляет файл сессии (используй только если совсем сломалось)."""
    path = Path(SESSION_PATH)
    if path.exists():
        path.unlink()
        print(f"Сессия удалена: {path}")
    else:
        print("Сессия не найдена")


def list_sessions() -> None:
    """Показывает все существующие сессии."""
    print("Найденные сессии:")
    for f in SESSIONS_DIR.glob("*.session"):
        print(f"   • {f.name}")


__all__ = ["get_client", "clear_session", "list_sessions", "SESSION_NAME"]
