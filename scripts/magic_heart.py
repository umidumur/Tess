#!/usr/bin/env python3
"""Magic Heart — автоответчик с анимацией сердец.

Реагирует на ключевые фразы, заданные в .env файле (MAGIC_PHRASES).
Полностью независимый скрипт.
"""

import asyncio
import json
import os
import sys
import time
from random import choice
from typing import Optional

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.events import NewMessage
from telethon.tl.functions.messages import SendReactionRequest, SetTypingRequest
from telethon.tl.types import DataJSON, ReactionEmoji, SendMessageEmojiInteraction

load_dotenv()

# ====================== ИМПОРТЫ ======================
from scripts.session_manager import get_client
from scripts.telegram_logger import telegram_log, validate_bot_config

# ====================== КОНФИГУРАЦИЯ ИЗ .env ======================
AUTO_REPLY_THREAD: int = int(os.getenv("AUTO_REPLY_THREAD", "0"))

# Ключевые фразы — теперь берутся из .env
# Пример в .env: MAGIC_PHRASES=magic,ily,люблю,heart,сердце
MAGIC_PHRASES_RAW = os.getenv("MAGIC_PHRASES", "magic,ily")
MAGIC_PHRASES: list[str] = [
    phrase.strip().lower() for phrase in MAGIC_PHRASES_RAW.split(",") if phrase.strip()
]

# Если в .env ничего не указано — используем дефолтные
if not MAGIC_PHRASES:
    MAGIC_PHRASES = ["magic", "ily"]

COOLDOWN_SECONDS: int = int(os.getenv("MAGIC_COOLDOWN", "300"))  # 5 минут по умолчанию

# ====================== КОНСТАНТЫ АНИМАЦИИ ======================
HEART = "🤍"

HEARTS = ["🤎", "🧡", "💙", "🖤", "💛", "💜", "❤️‍🔥", "💚", "❤️‍🩹", "💖", "❤"]

COLORED_HEARTS = ["❤", "💚", "💙", "💜", "❤️‍🩹", "❤️‍🔥", "💖", "💝"]

ANIMATED_HEARTS = ["🩷", "🧡", "💚", "💛", "🩵", "💜", "💙", "🤎", "🤍", "❤️"]

EDIT_DELAY = 0.20

# ====================== ASCII-КАРТЫ ======================
PARADE_MAP = """
000000000
001101100
011111110
011111110
011111110
001111100
000111000
000010000
000000000
"""

END_MAP = [
    """
000000000
001101100
010010010
010000010
010000010
001000100
000101000
000010000
000000000
""",
    """
111111111
110010011
101101101
101111101
101111101
110111011
111010111
111101111
111111111
""",
]

# ====================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ======================
client: TelegramClient = get_client()
last_triggered_time: dict = {}


def generate_parade_colored() -> str:
    """Генерирует парад случайно окрашенных сердец."""
    output = ""
    for c in PARADE_MAP:
        if c == "0":
            output += HEART
        elif c == "1":
            output += choice(COLORED_HEARTS)
        else:
            output += c
    return output


def generate_parade_hearts(num: int) -> str:
    """Генерирует парад с конкретным типом сердца."""
    output = ""
    for c in PARADE_MAP:
        if c == "0":
            output += HEART
        elif c == "1":
            output += HEARTS[num]
        else:
            output += c
    return output


def generate_end(num1: int, num2: int) -> str:
    """Генерирует финальную анимацию."""
    output = ""
    for c in END_MAP[num1]:
        if c == "0":
            output += HEART
        elif c == "1":
            output += HEARTS[num2]
        else:
            output += c
    return output


# ====================== АНИМАЦИИ ======================
async def process_love_words(event: NewMessage.Event, msgid: int):
    """Анимация текста 'i love you forever'."""
    peer = event.peer_id.user_id
    await client.edit_message(peer, msgid, "i")
    await asyncio.sleep(0.5)
    await client.edit_message(peer, msgid, "i love")
    await asyncio.sleep(0.5)
    await client.edit_message(peer, msgid, "i love you")
    await asyncio.sleep(0.5)
    await client.edit_message(peer, msgid, "i love you forever")
    await asyncio.sleep(0.5)
    await client.edit_message(peer, msgid, "i love you forever ❤️‍🩹")


async def process_hearts_carusel(event: NewMessage.Event, msgid: int):
    """Карусель анимированных сердец."""
    peer = event.peer_id.user_id
    for heart in ANIMATED_HEARTS:
        await client.edit_message(peer, msgid, heart)
        await asyncio.sleep(3)


async def send_emoji_reaction(event: NewMessage.Event, msgid: int, emoticon: str = "❤️"):
    """Отправка реакции."""
    try:
        await client(
            SendReactionRequest(
                peer=event.peer_id, msg_id=msgid, reaction=[ReactionEmoji(emoticon=emoticon)]
            )
        )
    except Exception as e:  # pylint: disable=broad-except
        await telegram_log(
            f"Ошибка реакции: {e}", topic_id=AUTO_REPLY_THREAD, level="ERROR"
        )


async def send_emoji_interaction(event: NewMessage.Event, msgid: int, emoticon: str = "❤️"):
    """Отправка взаимодействия (тап по эмодзи)."""
    try:
        interaction_json = {"v": 1, "a": [{"t": 0.0, "i": 5}, {"t": 0.2, "i": 5}]}
        await client(
            SetTypingRequest(
                peer=event.peer_id,
                top_msg_id=msgid,
                action=SendMessageEmojiInteraction(
                    emoticon=emoticon,
                    msg_id=msgid,
                    interaction=DataJSON(data=json.dumps(interaction_json)),
                ),
            )
        )
    except Exception:  # pylint: disable=broad-except
        pass  # тихо игнорируем


async def process_build_place(event: NewMessage.Event, msgid: int):
    """Построение сердца из строк."""
    peer = event.peer_id.user_id
    output = HEART
    for _ in range(8):
        output += HEART
        await client.edit_message(peer, msgid, output)
        await asyncio.sleep(EDIT_DELAY)

    for _ in range(8):
        output += "\n" + (9 * HEART)
        await client.edit_message(peer, msgid, output)
        await asyncio.sleep(EDIT_DELAY)


async def process_colored_heart(event: NewMessage.Event, msgid: int):
    """Цветное сердце."""
    peer = event.peer_id.user_id
    for i in range(11):
        text = generate_parade_hearts(i)
        await client.edit_message(peer, msgid, text)
        await asyncio.sleep(EDIT_DELAY)


async def process_colored_parade(event: NewMessage.Event, msgid: int):
    """Случайно окрашенный парад сердец."""
    peer = event.peer_id.user_id
    for _ in range(15):
        text = generate_parade_colored()
        await client.edit_message(peer, msgid, text)
        await asyncio.sleep(2 * EDIT_DELAY)


async def process_end(event: NewMessage.Event, msgid: int):
    """Финальная анимация."""
    peer = event.peer_id.user_id
    for i in range(11):
        for c in range(2):
            text = generate_end(c, i)
            await client.edit_message(peer, msgid, text)
            await asyncio.sleep(EDIT_DELAY)


async def process_destroy_place(event: NewMessage.Event, msgid: int):
    """Разрушение сердца (анимация исчезновения)."""
    try:
        messages = await client.get_messages(event.chat_id, limit=1)
        if not messages:
            return
        msg = messages[0] if isinstance(messages, list) else messages
        output = msg.message or ""

        if not output:
            return

        arr = output.split("\n")
        while arr:
            if arr:
                arr.pop(0)
            for i in range(len(arr)):
                if arr[i]:
                    arr[i] = arr[i][:-1]

            await client.edit_message(event.peer_id.user_id, msgid, "\n".join(arr))
            await asyncio.sleep(EDIT_DELAY)
    except Exception as e:  # pylint: disable=broad-except
        print(f"Ошибка в process_destroy_place: {e}")


async def process_reply(event: NewMessage.Event) -> Optional[int]:
    """Отправляет начальное сердце и возвращает его ID."""
    await client.send_message(event.peer_id.user_id, message=HEART, reply_to=event.message.id)
    messages = await client.get_messages(event.chat_id, limit=1)
    if messages:
        msg = messages[0] if isinstance(messages, list) else messages
        return msg.id
    return None


# ====================== ОСНОВНОЙ ХЕНДЛЕР ======================
@client.on(NewMessage(incoming=True))
async def handle_magic_heart(event: NewMessage.Event):
    """Основной обработчик магических фраз."""
    if not event.is_private:
        return

    message_text = (event.message.message or "").lower().strip()
    user_id = event.sender_id
    current_time = time.time()

    # Проверяем наличие любой ключевой фразы
    if not any(phrase in message_text for phrase in MAGIC_PHRASES):
        return

    # Cooldown защита
    if user_id in last_triggered_time:
        elapsed = current_time - last_triggered_time[user_id]
        if elapsed < COOLDOWN_SECONDS:
            await telegram_log(
                f"Игнорируем спам от пользователя {user_id} (cooldown)",
                topic_id=AUTO_REPLY_THREAD,
                level="WARNING",
            )
            return

    last_triggered_time[user_id] = current_time

    await telegram_log(
        f"Запущена магия сердец для пользователя {user_id} по фразе: {message_text}",
        topic_id=AUTO_REPLY_THREAD,
        level="INFO",
    )

    msgid = await process_reply(event)
    if not msgid:
        return

    # Последовательность анимаций
    try:
        await process_build_place(event, msgid)
        await process_colored_heart(event, msgid)
        await process_colored_parade(event, msgid)
        await process_end(event, msgid)
        await process_destroy_place(event, msgid)
        await process_love_words(event, msgid)
        await process_hearts_carusel(event, msgid)

        # Финальные взаимодействия
        for _ in range(50):
            await send_emoji_interaction(event, msgid)
            await asyncio.sleep(0.5)

        await send_emoji_reaction(event, event.message.id)

        await telegram_log(
            f"✅ Анимация сердец успешно завершена для пользователя {user_id}",
            topic_id=AUTO_REPLY_THREAD,
            level="INFO",
        )

    except Exception as e:  # pylint: disable=broad-except
        await telegram_log(
            f"Ошибка во время анимации: {e}", topic_id=AUTO_REPLY_THREAD, level="ERROR"
        )
    finally:
        # Очищаем cooldown после завершения
        if user_id in last_triggered_time:
            del last_triggered_time[user_id]


async def main():
    """Запуск Magic Heart."""
    print("[*] Magic Heart Auto-Reply запущен... Ctrl+C для остановки.")

    await telegram_log("Magic Heart Auto-Reply started", topic_id=AUTO_REPLY_THREAD, level="INFO")

    await client.start()
    await client.run_until_disconnected()


if __name__ == "__main__":
    if not validate_bot_config(require_chat=True):
        print("❌ Отсутствует BOT_TOKEN или TELEGRAM_CHAT_ID")
        sys.exit(1)

    asyncio.run(main())
