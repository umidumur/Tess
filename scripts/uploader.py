#!/usr/bin/env python3
"""Uploader — отвечает только за отправку файла в Telegram через user client."""

from pathlib import Path
from typing import Optional

from telethon import TelegramClient

from scripts.telegram_logger import telegram_log


async def upload_track(
    client: TelegramClient,
    filepath: Path,
    caption: str,
    chat_id: int,
    reply_to: Optional[int] = None,
) -> bool:
    """Загружает файл в указанный чат."""
    try:
        await client.send_file(
            entity=chat_id,
            file=str(filepath),
            caption=caption,
            parse_mode="markdown",
            reply_to=reply_to,
            force_document=False,  # отправлять как аудио
        )

        await telegram_log(f"Файл успешно отправлен в чат {chat_id}", level="INFO")
        return True

    except Exception as e:  # pylint: disable=broad-except
        await telegram_log(
            f"Ошибка отправки файла в чат {chat_id}: {e}", level="ERROR"
        )
        return False
    finally:
        # Удаляем файл после отправки
        if filepath.exists():
            try:
                filepath.unlink()
                await telegram_log(
                    f"Временный файл удалён: {filepath.name}", level="DEBUG"
                )
            except Exception:  # pylint: disable=broad-except
                pass
