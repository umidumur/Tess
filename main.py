#!/usr/bin/env python3
"""Главный User Client (Telethon).

Минимальный клиент, который:
- Управляет дочерними процессами
- Ловит входящие ссылки Яндекс Музыки в личных чатах
- Ловит исходящие команды /dl
- Делегирует скачивание и отправку файлов
- Все сообщения и уведомления отправляются только через telegram_log
"""

import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.events import NewMessage

load_dotenv()

from scripts.session_manager import get_client
from scripts.telegram_logger import telegram_log
from scripts.uploader import upload_track
from scripts.yandex_downloader import yandex_downloader

# ====================== КОНСТАНТЫ ======================
AUTO_REPLY_THREAD: int = int(os.getenv("AUTO_REPLY_THREAD", "0"))
YM_THREAD: int = int(os.getenv("YM_THREAD", "0"))
BIO_THREAD: int = int(os.getenv("BIO_THREAD", "0"))

BOT_STATE_FILE: Path = Path("bot_state.json")

# ====================== ГЛОБАЛЬНОЕ СОСТОЯНИЕ ======================
bot_processes: Dict[str, subprocess.Popen[Any]] = {}
bot_state: Dict[str, bool] = {}
client: Optional[TelegramClient] = None


def _load_bot_state() -> Dict[str, bool]:
    """Загружает состояние ботов из файла."""
    if not BOT_STATE_FILE.exists():
        return {}

    try:
        with open(BOT_STATE_FILE, encoding="utf-8") as f:
            data: Dict[str, bool] = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:  # pylint: disable=broad-except
        print(f"Ошибка загрузки состояния: {e}")
        return {}


def _save_bot_state(state: Dict[str, bool]) -> None:
    """Сохраняет состояние ботов."""
    try:
        with open(BOT_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:  # pylint: disable=broad-except
        print(f"Ошибка сохранения состояния: {e}")


async def start_bot(script_name: str) -> None:
    """Запускает дочерний скрипт."""
    global bot_processes, bot_state

    if script_name in bot_processes and bot_processes[script_name].poll() is None:
        await telegram_log(f"{script_name} уже работает", level="WARNING")
        return

    try:
        proc = subprocess.Popen(
            [sys.executable, "-u", script_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=Path(__file__).parent,
            text=True,
        )
        bot_processes[script_name] = proc
        bot_state[script_name] = True
        _save_bot_state(bot_state)

        await telegram_log(f"{script_name} успешно запущен (PID {proc.pid})", level="INFO")
        print(f"✅ {script_name} запущен (PID {proc.pid})")
    except Exception as e:  # pylint: disable=broad-except
        await telegram_log(f"Не удалось запустить {script_name}: {e}", level="ERROR")


async def stop_bot(script_name: str) -> None:
    """Останавливает дочерний процесс."""
    global bot_processes, bot_state

    if script_name not in bot_processes or bot_processes[script_name].poll() is not None:
        await telegram_log(f"{script_name} не запущен", level="WARNING")
        return

    proc = bot_processes[script_name]
    proc.terminate()
    try:
        proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        proc.kill()

    del bot_processes[script_name]
    bot_state.pop(script_name, None)
    _save_bot_state(bot_state)

    await telegram_log(f"{script_name} остановлен", level="INFO")
    print(f"🛑 {script_name} остановлен")


async def restore_bots() -> None:
    """Восстанавливает ранее запущенные боты."""
    global bot_processes
    for script_name, should_run in list(bot_state.items()):
        if should_run and (
            script_name not in bot_processes or bot_processes[script_name].poll() is not None
        ):
            await start_bot(script_name)


# ====================== ОБРАБОТЧИКИ ======================


async def handle_yandex_link(event: NewMessage.Event) -> None:
    """Обрабатывает входящие ссылки Яндекс Музыки в личных чатах."""
    if not event.is_private:
        return

    message_text = (event.message.text or "").strip()

    if not re.search(
        r"(?:https?://)?(?:music\.)?yandex\.(?:ru|com|kz|uz)/(?:track|album)/",
        message_text,
        re.IGNORECASE,
    ):
        return

    await telegram_log(
        f"Получена ссылка ЯМ в личке: {message_text}", topic_id=YM_THREAD, level="INFO"
    )

    result = await yandex_downloader.download_track(message_text)
    if not result:
        await telegram_log("Не удалось скачать трек по ссылке", level="ERROR")
        return

    filepath, caption = result

    success = await upload_track(
        client=client,  # type: ignore
        filepath=filepath,
        caption=caption,
        chat_id=event.chat_id,
        reply_to=event.message.id,
    )

    if success:
        await telegram_log("Трек успешно скачан и отправлен пользователю", level="INFO")
    else:
        await telegram_log("Ошибка при отправке трека пользователю", level="ERROR")


async def handle_dl_command(event: NewMessage.Event) -> None:
    """Обрабатывает исходящую команду /dl."""
    text = event.message.text.strip()
    if not text.startswith("/dl"):
        return

    parts = text.split(maxsplit=1)
    identifier = parts[1] if len(parts) > 1 else None

    await telegram_log(f"Получена команда /dl: {identifier or 'текущий трек'}", level="INFO")

    if not identifier:
        from scripts.yandex_ynison import get_current_track_info

        track_info = await get_current_track_info()
        if track_info and track_info.get("is_playing"):
            identifier = track_info["track_id"]
        else:
            await telegram_log("Команда /dl без ссылки и ничего не играет", level="WARNING")
            return

    result = await yandex_downloader.download_track(identifier)
    if not result:
        await telegram_log("Не удалось скачать трек по команде /dl", level="ERROR")
        return

    filepath, caption = result

    success = await upload_track(
        client=client,  # type: ignore
        filepath=filepath,
        caption=caption,
        chat_id=event.chat_id,
        reply_to=event.message.id,
    )

    if success:
        await telegram_log("Трек по команде /dl успешно отправлен", level="INFO")
    else:
        await telegram_log("Ошибка отправки трека по команде /dl", level="ERROR")


async def handle_commands(event: NewMessage.Event) -> None:
    """Обработка управляющих команд (только исходящие)."""

    text = event.message.text.lower().strip()

    if text == "/help":
        help_text = """**Доступные команды:**

**Скачивание:**
• `/dl` — скачать текущий трек
• `/dl <ссылка>` — скачать по ссылке

**Управление:**
• `/start_ym_sync` — запустить обновление био
• `/start_magic` — запустить Magic Heart
• `/start_all` — запустить всё
• `/stop_ym_sync` — остановить био
• `/stop_magic` — остановить Magic Heart
• `/stop_all` — остановить всё

**Статус:** `/status`
**Помощь:** `/help`"""
        await event.reply(help_text)
        return

    if text == "/status":
        if not bot_processes:
            await event.reply("Сейчас ничего не запущено")
            return

        lines = ["**Статус ботов:**"]
        for name, proc in bot_processes.items():
            code = proc.poll()
            status = "Работает" if code is None else f"Остановлен (код {code})"
            lines.append(f"• {name}: {status}")
        await event.reply("\n".join(lines))
        return

    # Запуск
    if text == "/start_ym_sync":
        await start_bot("scripts/yandex_sync.py")
    elif text == "/start_magic" or text == "/start_auto_reply":
        await start_bot("scripts/magic_heart.py")
    elif text == "/start_all":
        await start_bot("scripts/yandex_sync.py")
        await start_bot("scripts/magic_heart.py")

    # Остановка
    elif text == "/stop_ym_sync":
        await stop_bot("scripts/yandex_sync.py")
    elif text == "/stop_magic" or text == "/stop_auto_reply":
        await stop_bot("scripts/magic_heart.py")
    elif text == "/stop_all":
        for name in list(bot_processes.keys()):
            await stop_bot(name)
        _save_bot_state({})


# ====================== ЗАПУСК ======================
async def main() -> None:
    """Главная функция."""
    global client, bot_state

    bot_state = _load_bot_state()

    try:
        client = get_client()
    except Exception as e:  # pylint: disable=broad-except
        await telegram_log(f"Не удалось создать TelegramClient: {e}", level="ERROR")
        sys.exit(1)

    # Регистрация обработчиков
    client.add_event_handler(handle_yandex_link, events.NewMessage(incoming=True))
    client.add_event_handler(handle_dl_command, events.NewMessage(outgoing=True))
    client.add_event_handler(handle_commands, events.NewMessage(outgoing=True))

    await client.start()
    await telegram_log("Главный User Client успешно запущен", level="INFO")
    print("✅ Главный User Client запущен")

    await restore_bots()

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
