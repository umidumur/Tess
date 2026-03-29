#!/usr/bin/env python3
"""Yandex Music Ynison client — получение текущего трека."""

import asyncio
import json
import logging
import os
import random
import string
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp
from dotenv import load_dotenv
from yandex_music import ClientAsync

load_dotenv()

logger = logging.getLogger(__name__)

# Импортируем telegram_log правильно
try:
    from scripts.telegram_logger import telegram_log
except ImportError:
    telegram_log = None
    logger.warning("telegram_log не найден, логи в Telegram будут отключены")

TOKEN: str = os.getenv("YANDEX_MUSIC_AUTH_TOKEN") or ""
if not TOKEN:
    raise ValueError("YANDEX_MUSIC_AUTH_TOKEN не задан в .env")

yandex_client: Optional[ClientAsync] = None


def generate_device_id(length: int = 16) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=length))


async def get_yandex_client() -> Optional[ClientAsync]:
    global yandex_client
    if yandex_client is not None:
        return yandex_client

    try:
        yandex_client = await ClientAsync(TOKEN).init()
        logger.info("✅ Yandex Music ClientAsync инициализирован")
        return yandex_client
    except Exception as e:  # pylint: disable=broad-except
        logger.error("Не удалось инициализировать Yandex Music клиент: %s", e)
        if telegram_log:
            await telegram_log(f"Yandex client init failed: {e}", level="ERROR")
        return None


async def create_ynison_ws(ya_token: str, ws_proto: dict) -> dict:
    redirect_url = (
        "wss://ynison.music.yandex.ru/redirector.YnisonRedirectService/GetRedirectToYnison"
    )

    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(
            redirect_url,
            headers={
                "Sec-WebSocket-Protocol": f"Bearer, v2, {json.dumps(ws_proto)}",
                "Origin": "http://music.yandex.ru",
                "Authorization": f"OAuth {ya_token}",
            },
            timeout=10,
        ) as ws:
            response = await ws.receive()
            return json.loads(response.data)


async def get_current_track_info() -> Optional[Dict[str, Any]]:
    """Получает информацию о текущем треке."""
    client = await get_yandex_client()
    if client is None:
        return None

    for attempt in range(1, 4):
        try:
            device_id = generate_device_id()

            ws_proto = {
                "Ynison-Device-Id": device_id,
                "Ynison-Device-Info": json.dumps({"app_name": "Chrome", "type": 1}),
            }

            data = await create_ynison_ws(TOKEN, ws_proto)
            ws_proto["Ynison-Redirect-Ticket"] = data["redirect_ticket"]

            payload = {
                "update_full_state": {
                    "player_state": {
                        "player_queue": {
                            "current_playable_index": -1,
                            "entity_id": "",
                            "entity_type": "VARIOUS",
                            "playable_list": [],
                            "options": {"repeat_mode": "NONE"},
                            "entity_context": "BASED_ON_ENTITY_BY_DEFAULT",
                            "version": {
                                "device_id": device_id,
                                "version": 9021243204784341000,
                                "timestamp_ms": int(time.time() * 1000),
                            },
                            "from_optional": "",
                        },
                        "status": {
                            "duration_ms": 0,
                            "paused": True,
                            "playback_speed": 1,
                            "progress_ms": 0,
                            "version": {
                                "device_id": device_id,
                                "version": 8321822175199937000,
                                "timestamp_ms": int(time.time() * 1000),
                            },
                        },
                    },
                    "device": {
                        "capabilities": {
                            "can_be_player": True,
                            "can_be_remote_controller": False,
                            "volume_granularity": 16,
                        },
                        "info": {
                            "device_id": device_id,
                            "type": "WEB",
                            "title": "Chrome Browser",
                            "app_name": "Chrome",
                        },
                        "volume_info": {"volume": 0},
                        "is_shadow": True,
                    },
                    "is_currently_active": False,
                },
                "rid": str(uuid.uuid4()),
                "player_action_timestamp_ms": int(time.time() * 1000),
                "activity_interception_type": "DO_NOT_INTERCEPT_BY_DEFAULT",
            }

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.ws_connect(
                    f"wss://{data['host']}/ynison_state.YnisonStateService/PutYnisonState",
                    headers={
                        "Sec-WebSocket-Protocol": f"Bearer, v2, {json.dumps(ws_proto)}",
                        "Origin": "http://music.yandex.ru",
                        "Authorization": f"OAuth {TOKEN}",
                    },
                    timeout=10,
                ) as ws:
                    await ws.send_str(json.dumps(payload))
                    response = await ws.receive()
                    ynison = json.loads(response.data)

            # Сохраняем отладочную информацию
            Path("ynison_data.json").write_text(
                json.dumps(ynison, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            # Извлечение трека
            playable_list = (
                ynison.get("player_state", {}).get("player_queue", {}).get("playable_list", [])
            )
            if not playable_list:
                logger.warning("Нет треков в очереди")
                return None

            current_index = (
                ynison.get("player_state", {})
                .get("player_queue", {})
                .get("current_playable_index", -1)
            )
            if current_index < 0:
                return None

            track_info = playable_list[current_index]
            track_id = track_info["playable_id"]

            # ←←← КРИТИЧЕСКАЯ ЧАСТЬ: Получаем информацию о треке с таймаутом
            try:
                track = (await asyncio.wait_for(client.tracks(track_id), timeout=8.0))[0]
            except asyncio.TimeoutError:
                logger.error("Таймаут при запросе информации о треке")
                continue
            except Exception as e:  # pylint: disable=broad-except
                logger.error("Ошибка при получении трека %s: %s", track_id, e)
                continue

            artists = (
                ", ".join(str(artist.name) for artist in track.artists if artist.name)
                or "Unknown Artist"
            )

            logger.info(
                "Now Playing: %s by %s | Playing: %s",
                track.title,
                artists,
                not ynison.get("player_state", {}).get("status", {}).get("paused", True),
            )

            return {
                "title": track.title,
                "artists": artists,
                "album": track.albums[0].title if track.albums else "Unknown Album",
                "is_playing": not ynison.get("player_state", {})
                .get("status", {})
                .get("paused", True),
                "track_id": track_id,
            }

        except Exception:  # pylint: disable=broad-except
            logger.error("Попытка %d/3 провалилась", attempt, exc_info=True)
            await asyncio.sleep(2)

    logger.error("Не удалось получить трек после 3 попыток")
    return None
