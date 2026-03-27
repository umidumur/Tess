import subprocess
import sys
import json
from pathlib import Path
from telethon import TelegramClient
from telethon.events import NewMessage
from scripts.session_manager import get_client
from scripts.telegram_logger import telegram_log
from scripts.yandex_sync import download_track
from dotenv import load_dotenv

# Инициализируем клиента для main бота
client = get_client()
load_dotenv()
# Thread/topic IDs from environment (fallback to 0 if unset)
import os
AUTO_REPLY_THREAD = int(os.getenv("AUTO_REPLY_THREAD", "0"))
YM_THREAD = int(os.getenv("YM_THREAD", "0"))

# Bot state persistence
BOT_STATE_FILE = Path("bot_state.json")
# Словарь для хранения процессов ботов
bot_processes = {}

def load_bot_state():
    """Load which bots should be running from persistent storage"""
    if BOT_STATE_FILE.exists():
        try:
            with open(BOT_STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Failed to load bot state: {e}")
    return {}

def save_bot_state(state):
    """Save bot state to persistent storage"""
    try:
        with open(BOT_STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"Failed to save bot state: {e}")

# Load initial state
bot_state = load_bot_state()

async def start_bot(script_name):
    """Запускает указанный бот-скрипт в отдельном процессе"""
    if script_name not in bot_processes or bot_processes[script_name].poll() is not None:
        process = subprocess.Popen([sys.executable, script_name])
        bot_processes[script_name] = process
        # Save to persistent state
        bot_state[script_name] = True
        save_bot_state(bot_state)
        print(f"{script_name} запущен")
    else:
        print(f"{script_name} уже запущен")

async def stop_bot(script_name):
    """Останавливает указанный бот-скрипт"""
    if script_name in bot_processes and bot_processes[script_name].poll() is None:
        bot_processes[script_name].terminate()
        print(f"{script_name} остановлен")
        del bot_processes[script_name]
        # Remove from persistent state
        bot_state.pop(script_name, None)
        save_bot_state(bot_state)
    else:
        print(f"{script_name} не запущен")

async def restore_bots():
    """Restore and start bots that were running before restart"""
    for script_name, should_run in bot_state.items():
        if should_run:
            await start_bot(script_name)
            print(f"Auto-starting {script_name}")

@client.on(NewMessage())
async def handle_track_url(event: NewMessage.Event):
    track_dt = None
    # Yandex Music track link detection (supports ru/com/kz/uz, with or without protocol)
    import re
    message_text = (event.message.text or "").strip()
    if re.search(
        r"(?:https?://)?(?:music\.)?yandex\.(?:ru|com|kz|uz)/(?:track|album)/",
        message_text,
        re.IGNORECASE,
    ):
        await telegram_log(
            f"Yandex link detected, message_text={message_text}",
            topic_id=YM_THREAD,
            level='DEBUG'
        )
        track_dt = await download_track(event.peer_id, message_text)

    elif message_text.startswith('/dl'):
        await telegram_log(
            f"/dl command received, message_text={message_text}",
            topic_id=YM_THREAD,
            level='DEBUG'
        )
        # Check if URL is provided after /dl command
        parts = event.message.text.strip().split(None, 1)
        if len(parts) > 1:
            url = parts[1]
            track_dt = await download_track(event.peer_id, url)
        else:
            track_dt = await download_track(event.peer_id)
   
    # Upload to Telegram
    if track_dt:
        try:
            filepath = track_dt[0]
            track_caption = track_dt[1]
            
            # Отправляем сообщение с прогрессом
            progress_msg = await client.send_message(
                event.peer_id,
                "Upload progress: 0%",
                reply_to=event.message.id
            )

            def _progress(sent: int, total: int) -> None:
                if total:
                    percent = sent / total * 100
                    # Schedule the async edit without awaiting inside the callback
                    client.loop.create_task(
                        client.edit_message(
                            event.peer_id,
                            progress_msg.id,
                            f"Upload progress: {percent:.2f}%"
                        )
                    )

            try:
                await client.send_file(
                    event.peer_id,
                    filepath,
                    caption=track_caption,
                    progress_callback=_progress,
                    force_document=False,
                    reply_to=event.message.id,
                    message_effect_id=5159385139981059251
                )
            finally:
                # Удаляем сообщение с прогрессом после завершения
                await client.delete_messages(event.peer_id, [progress_msg.id])
            
            # Delete file after successful upload
            import os
            try:
                os.remove(filepath)
                print(f"Deleted file: {filepath}")
            except Exception as e:
                print(f"Failed to delete file: {e}")

        except Exception as e:
            print(f"Error uploading to Telegram: {e}")

@client.on(NewMessage(outgoing=True))
async def handle_outgoing_message(event: NewMessage.Event):
    if event.is_private:  # Только личные сообщения
        message_text = event.message.text.lower()
        
        # Help command
        if message_text == '/help':
            help_text = """**Available Commands:**
    • `/dl` - Download last listened track on Yandex Music
    • You can also send Yandex Music track or album links directly.

**Start:**
    • `/start_auto_reply` - Start magic heart bot
    • `/start_ym_sync` - Start Yandex Music sync
    • `/start_all` - Start all bots

**Stop:**
    • `/stop_auto_reply` - Stop magic heart bot
    • `/stop_ym_sync` - Stop Yandex Music sync
    • `/stop_all` - Stop all bots

**Info:**
    • `/status` - Show running bots status
    • `/help` - Show this help message"""
            await event.reply(help_text)
        
        # Status command
        elif message_text == '/status':
            if not bot_processes:
                await event.reply('No bots are currently running')
            else:
                status_lines = ['**Running Bots:**']
                for name, process in bot_processes.items():
                    if process.poll() is None:
                        status_lines.append(f'✅ {name} - Running')
                    else:
                        status_lines.append(f'❌ {name} - Stopped')
                await event.reply('\n'.join(status_lines))
        
        # Start commands
        elif message_text == '/start_auto_reply':
            await start_bot('scripts/magic_heart.py')
            await event.reply('Magic heart started')
        elif message_text == '/start_ym_sync':
            await start_bot('scripts/yandex_sync.py')
            await event.reply('Yandex sync started')
        elif message_text == '/start_all':
            await start_bot('scripts/magic_heart.py')
            await start_bot('scripts/yandex_sync.py')
            await event.reply('All bots started')
        
        # Stop commands
        elif message_text == '/stop_auto_reply':
            await stop_bot('scripts/magic_heart.py')
            await event.reply('Magic heart stopped')
            await telegram_log('Magic heart bot stopped by user', topic_id=AUTO_REPLY_THREAD, level='INFO')
        elif message_text == '/stop_ym_sync':
            await stop_bot('scripts/yandex_sync.py')
            await event.reply('Yandex sync stopped')
            await telegram_log('Yandex sync bot stopped by user', topic_id=YM_THREAD, level='INFO')
        
        # Stop all
        elif message_text == '/stop_all':
            for name, process in bot_processes.items():
                if process.poll() is None:
                    process.terminate()
                    print(f"{name} stopped")
            bot_processes.clear()
            await event.reply('All bots stopped')

if __name__ == '__main__':
    client.start()
    # Restore bots that were running before restart
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(restore_bots())
    client.run_until_disconnected()
