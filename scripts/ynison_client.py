import json
import logging
from typing import Optional, Dict, Any
from aiohttp import ClientSession

logger = logging.getLogger(__name__)

class YnisonClient:
    """
    Простой клиент для получения информации о текущем треке через Ynison API.
    """
    
    def __init__(self, token: str):
        self.token = token
        self.ws_proto = {
            "method": "subscribe",
            "jsonrpc": "2.0",
            "id": "1",
            "params": {
                "context": "default",
                "contextItem": "",
                "device": {
                    "deviceId": "web",
                    "deviceType": "web",
                    "timestamp": 0,
                    "appName": "ymusic",
                    "appVersion": "0.0.0",
                    "packageName": "ru.yandex.music"
                }
            }
        }

    async def get_current_track_info(self) -> Optional[Dict[Any, Any]]:
        """
        Получить информацию о текущем треке.
        
        Returns:
            Словарь с информацией о треке или None, если ошибка/нет трека.
        """
        payload = {
            "method": "getCurrentState",
            "jsonrpc": "2.0",
            "id": "1",
            "params": {}
        }

        try:
            async with ClientSession() as session:
                # Получаем host для WebSocket
                async with session.get(
                    "https://api.music.yandex.ru/",
                    headers={"Authorization": f"OAuth {self.token}"}
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"Failed to get Ynison host: {resp.status}")
                        return None
                    data = await resp.json()
                    host = data.get('result', {}).get('host')
                    if not host:
                        logger.error("No host found in Ynison response")
                        return None

                # Подключаемся к WebSocket
                async with session.ws_connect(
                    f"wss://{host}/ynison_state.YnisonStateService/PutYnisonState",
                    headers={
                        "Sec-WebSocket-Protocol": f"Bearer, v2, {json.dumps(self.ws_proto)}",
                        "Origin": "http://music.yandex.ru",
                        "Authorization": f"OAuth {self.token}",
                    },
                ) as ws:
                    await ws.send_str(json.dumps(payload))
                    response = await ws.receive()
                    ynison_data = json.loads(response.data)

                    # Сохраняем данные (опционально)
                    with open('ynison_C_data.json', 'w', encoding='utf-8') as f:
                        json.dump(ynison_data, f, ensure_ascii=False, indent=2)

                    return ynison_data

        except Exception as e:
            logger.error(f"Error getting current track info: {e}")
            return None

    def extract_track_details(self, ynison_data: Dict[Any, Any]) -> Optional[Dict[str, Any]]:
        """
        Извлечь важные детали трека из ynison_data.
        
        Returns:
            Словарь с is_playing, track_id, progress, context и т.д.
        """
        try:
            result = ynison_data.get('result', {})
            if not result:
                return None

            return {
                'is_playing': result.get('isPlaying', False),
                'track_id': result.get('trackId'),
                'progress_ms': result.get('progressMs'),
                'duration_ms': result.get('durationMs'),
                'context': result.get('context'),
                'context_item': result.get('contextItem'),
                'queue_item': result.get('queueItem'),
            }
        except Exception as e:
            logger.error(f"Error extracting track details: {e}")
            return None

# Пример использования
async def main():
    token = "y0__xCK_Nv0Bhje-AYgjbTPmhUwwce72wdlzqPQkDfcWjyfT9Nh5f82qzobJQ"
    client = YnisonClient(token)
    
    info = await client.get_current_track_info()
    if info:
        details = client.extract_track_details(info)
        print(f"Current track info: {details}")
    else:
        print("No track info available")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())