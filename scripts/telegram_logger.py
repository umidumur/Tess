#!/usr/bin/env python3
"""Telegram Logger — асинхронный логгер с уровнями отправки в Telegram.

Поддерживает 3 уровня отправки сообщений в Telegram:
    0 — только ERROR и WARNING (всегда отправляются)
    1 — ERROR, WARNING, INFO
    2 — все уровни (DEBUG + INFO + WARNING + ERROR)
"""

import asyncio
import html
import logging
import os
from typing import Optional, Union

import aiohttp
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ====================== КОНФИГУРАЦИЯ ======================
# Уровень логирования для Telegram (0, 1 или 2)
TELEGRAM_LOG_LEVEL: int = int(os.getenv("TELEGRAM_LOG_LEVEL", "1"))

# Emoji для каждого уровня
LOG_LEVEL_EMOJIS = {
    "DEBUG": "🔍",
    "INFO": "ℹ️",
    "WARNING": "⚠️",
    "ERROR": "❌",
}

# Какой уровень соответствует какому числу
LEVEL_PRIORITY = {
    "DEBUG": 2,
    "INFO": 1,
    "WARNING": 0,
    "ERROR": 0,
}


def _should_send_to_telegram(level: str) -> bool:
    """Проверяет, нужно ли отправлять сообщение данного уровня в Telegram."""
    level = level.upper()
    required_priority = LEVEL_PRIORITY.get(level, 1)  # по умолчанию INFO

    return TELEGRAM_LOG_LEVEL >= required_priority


async def telegram_log(
    message: str,
    chat_id: Optional[Union[str, int]] = None,
    topic_id: Optional[int] = None,
    level: str = "INFO",
) -> bool:
    """Отправляет лог-сообщение в Telegram с учётом уровня TELEGRAM_LOG_LEVEL.

    Args:
        message: Текст сообщения.
        chat_id: ID чата/группы (если не указан — берётся из TELEGRAM_CHAT_ID).
        topic_id: ID топика (для тем в группе).
        level: Уровень сообщения: DEBUG, INFO, WARNING, ERROR.

    Returns:
        True — если сообщение успешно отправлено в Telegram.
    """
    # 1. Сначала всегда пишем в локальный лог
    log_method = getattr(logger, level.lower(), logger.info)
    log_method("[TELEGRAM] %s", message)

    # 2. Проверяем, нужно ли отправлять в Telegram
    if not _should_send_to_telegram(level):
        return False  # тихо пропускаем, но уже записали в файл

    # 3. Проверяем конфигурацию
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.error("BOT_TOKEN не задан в .env")
        return False

    if not chat_id:
        chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not chat_id:
        logger.error("chat_id не указан и TELEGRAM_CHAT_ID не задан")
        return False

    # Нормализуем chat_id
    try:
        if isinstance(chat_id, str) and chat_id.lstrip("-").isdigit():
            chat_id = int(chat_id)
    except Exception:  # pylint: disable=broad-except
        pass

    # Форматируем сообщение
    emoji = LOG_LEVEL_EMOJIS.get(level.upper(), "📝")
    formatted_message = f"{emoji} <b>[{level}]</b> {html.escape(message)}"

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": formatted_message,
        "parse_mode": "HTML",
    }

    if topic_id is not None:
        try:
            tid = int(topic_id)
            if tid > 0:
                payload["message_thread_id"] = tid
        except Exception:  # pylint: disable=broad-except
            logger.debug("Некорректный topic_id: %r", topic_id)

    # Отправка
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    logger.debug("Сообщение успешно отправлено в Telegram")
                    return True
                else:
                    text = await response.text()
                    logger.error(
                        "Не удалось отправить лог в Telegram. Status: %s, Response: %s",
                        response.status,
                        text[:500],
                    )
                    return False

    except asyncio.TimeoutError:
        logger.error("Таймаут при отправке лога в Telegram")
        return False
    except Exception as e:  # pylint: disable=broad-except
        logger.error("Ошибка при отправке в Telegram: %s", e)
        return False


def telegram_log_sync(
    message: str,
    chat_id: Optional[Union[str, int]] = None,
    topic_id: Optional[int] = None,
    level: str = "INFO",
) -> bool:
    """Синхронная обёртка (на случай, если вызов из не-async контекста)."""
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            logger.warning("telegram_log_sync вызван из async контекста. Используйте telegram_log.")
            return False
        return loop.run_until_complete(telegram_log(message, chat_id, topic_id, level))
    except RuntimeError:
        # Нет запущенного loop
        return asyncio.run(telegram_log(message, chat_id, topic_id, level))


def validate_bot_config(require_chat: bool = True) -> bool:
    """Проверяет наличие необходимых переменных окружения."""
    bot_token = os.getenv("BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    ok = True

    if not bot_token:
        logger.error("BOT_TOKEN не задан в .env")
        ok = False
    if require_chat and not chat:
        logger.error("TELEGRAM_CHAT_ID не задан в .env")
        ok = False

    return ok


__all__ = ["telegram_log", "telegram_log_sync", "validate_bot_config"]
