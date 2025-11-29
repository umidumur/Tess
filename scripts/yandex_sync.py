"""Yandex Music to Telegram bio synchronization script.

This module synchronizes currently playing track information from Yandex Music
to the user's Telegram bio. It updates the bio when music is playing and
restores the original bio when playback stops.
"""

import asyncio
import json
import logging
import os
import random
import string
import sys
from pathlib import Path
from typing import Optional

from aiohttp import ClientSession
from dotenv import load_dotenv
from mutagen.id3 import ID3
from mutagen.id3._frames import APIC, TALB, TIT2, TPE1
from mutagen.mp3 import MP3
from telethon.errors import AboutTooLongError, FloodWaitError
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.events import NewMessage
from yandex_music import ClientAsync

# Add parent directory to path for imports
sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from scripts.session_manager import get_client
from scripts.telegram_logger import telegram_log

load_dotenv()
client_tg = get_client("YandexSync")

# Logging configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()  # Default: INFO, can be DEBUG
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    filename="log.log",
    format="[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s",
    encoding='utf-8'
)
logger = logging.getLogger(__name__)

TOKEN: str = os.getenv("YANDEX_MUSIC_AUTH_TOKEN") or ""
if not TOKEN:
    raise ValueError("YANDEX_MUSIC_AUTH_TOKEN environment variable not set.")

INITIAL_BIO: str = os.getenv("INITIAL_BIO") or ""
YM_THREAD: int = int(os.getenv("YM_THREAD", "0"))
BIO_THREAD: int = int(os.getenv("BIO_THREAD", "0"))
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads")

# Bio key to identify bot-managed bios
# NEVER use this key in your original bio!
KEY = "🎶"

# Bio format templates (tried in order, most detailed first)
BIOS = [
    KEY + " Now Playing: {title} - {artists} {progress}/{duration}",
    KEY + " Now Playing: {title} - {artists}",
    KEY + " : {title} - {artists}",
    KEY + " Now Playing: {title}",
    KEY + " : {title}",
]

OFFSET = 2  # Reserve chars for safety margin
LIMIT = 140 - OFFSET


class BioDatabase:
    """Manages user bio and bot-managed state persistence.
    
    Attributes:
        db_file: Path to JSON database file.
        db: In-memory database dictionary.
    """

    def __init__(self, db_file: str = "database.json"):
        """Initialize database manager.
        
        Args:
            db_file: Path to JSON database file (default: database.json).
        """
        self.db_file = db_file
        self.db = self._load()

    def _load(self) -> dict:
        """Load database from file.
        
        Returns:
            Dictionary containing database contents.
        """
        try:
            with open(self.db_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def _save(self) -> None:
        """Persist database to file."""
        with open(self.db_file, 'w', encoding='utf-8') as f:
            json.dump(self.db, f, indent=2, ensure_ascii=False)

    def get_user_bio(self) -> str:
        """Get the user's original bio (not managed by bot)."""
        return self.db.get("user_bio", INITIAL_BIO or "")

    def set_user_bio(self, bio: str) -> None:
        """Save the user's original bio."""
        self.db["user_bio"] = bio
        self._save()

    def get_bot_bio(self) -> str:
        """Get the last bio set by bot."""
        return self.db.get("bot_bio", "")

    def set_bot_bio(self, bio: str) -> None:
        """Save the bio that was set by bot."""
        self.db["bot_bio"] = bio
        self._save()


bio_db = BioDatabase()


def ms_converter(millis):
    """Convert milliseconds to MM:SS format.
    
    Args:
        millis: Time in milliseconds.
        
    Returns:
        Formatted time string (e.g., "3:45").
    """
    millis = int(millis)
    seconds = (millis / 1000) % 60
    seconds = int(seconds)
    if str(seconds) == "0":
        seconds = "00"
    if len(str(seconds)) == 1:
        seconds = "0" + str(seconds)
    minutes = (millis / (1000 * 60)) % 60
    minutes = int(minutes)
    return str(minutes) + ":" + str(seconds)


def generate_device_id(length: int = 16) -> str:
    """Generate random device ID.
    
    Args:
        length: Length of device ID (default: 16).
        
    Returns:
        Random lowercase string of specified length.
    """
    return "".join(random.choices(string.ascii_lowercase, k=length))


async def create_ynison_ws(ya_token: str, ws_proto: dict) -> dict:
    """Create Ynison WebSocket connection and get redirect info.
    
    Args:
        ya_token: Yandex Music OAuth token.
        ws_proto: WebSocket protocol headers dictionary.
        
    Returns:
        Dictionary with redirect information including host and ticket.
    """
    redirect_url = (
        "wss://ynison.music.yandex.ru/redirector."
        "YnisonRedirectService/GetRedirectToYnison"
    )
    async with ClientSession() as session:
        async with session.ws_connect(
            redirect_url,
            headers={
                "Sec-WebSocket-Protocol": (
                    f"Bearer, v2, {json.dumps(ws_proto)}"
                ),
                "Origin": "http://music.yandex.ru",
                "Authorization": f"OAuth {ya_token}",
            },
        ) as ws:
            response = await ws.receive()
            return json.loads(response.data)


async def get_current_track_info():
    """Fetch currently-playing track from Yandex Music using Ynison.
    
    Uses the Ynison WebSocket protocol to query the current player state
    and retrieve detailed information about the currently playing track.
    
    Returns:
        Dictionary with track info (title, artists, album, duration, etc.)
        or None if no track is playing or an error occurred.
    """
    try:
        client = await ClientAsync(TOKEN).init()
        logger.info("Yandex Music client initialized successfully.")
        logger.debug(
            f"Initialized ClientAsync with token: {TOKEN[:20]}..."
        )
    except Exception as e:
        error_msg = f"Error initializing Yandex Music client: {e}"
        logger.error(error_msg)
        await telegram_log(
            error_msg,
            topic_id=YM_THREAD,
            level="ERROR"
        )
        return None

    try:
        device_id = generate_device_id()
        ws_proto = {
            "Ynison-Device-Id": device_id,
            "Ynison-Device-Info": json.dumps({"app_name": "Chrome", "type": 1}),
        }
        
        # Get redirect ticket
        if not TOKEN:
            raise ValueError("YANDEX_MUSIC_AUTH_TOKEN is empty")
        data = await create_ynison_ws(TOKEN, ws_proto)
        ws_proto["Ynison-Redirect-Ticket"] = data["redirect_ticket"]

        # Build payload to query player state
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
                            "timestamp_ms": 0,
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
                            "timestamp_ms": 0,
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
            "rid": "ac281c26-a047-4419-ad00-e4fbfda1cba3",
            "player_action_timestamp_ms": 0,
            "activity_interception_type": "DO_NOT_INTERCEPT_BY_DEFAULT",
        }

        # Connect to Ynison state service and get player state
        async with ClientSession() as session:
            async with session.ws_connect(
                f"wss://{data['host']}/ynison_state.YnisonStateService/PutYnisonState",
                headers={
                    "Sec-WebSocket-Protocol": f"Bearer, v2, {json.dumps(ws_proto)}",
                    "Origin": "http://music.yandex.ru",
                    "Authorization": f"OAuth {TOKEN}",
                },
            ) as ws:
                await ws.send_str(json.dumps(payload))
                response = await ws.receive()
                ynison = json.loads(response.data)

                # Write ynison data to file
                with open('ynison_data.json', 'w', encoding='utf-8') as f:
                    json.dump(ynison, f, ensure_ascii=False, indent=2)

        # Extract current track
        if not ynison["player_state"]["player_queue"]["playable_list"]:
            warning_msg = "No tracks in queue"
            logger.warning(warning_msg)
            await telegram_log(warning_msg, topic_id=YM_THREAD, level="WARNING")
            return None

        current_index = ynison["player_state"]["player_queue"]["current_playable_index"]
        if current_index < 0:
            logger.debug("Nothing currently playing (index < 0)")
            return None

        track_info = ynison["player_state"]["player_queue"]["playable_list"][current_index]
        track_id = track_info["playable_id"]
        
        # Get track details
        track = (await client.tracks(track_id))[0]
        
        if track.artists:
            artists = ", ".join([
                str(artist.name)
                for artist in track.artists
                if artist.name
            ])
        else:
            artists = "Unknown Artist"
        
        title = track.title
        album = (
            track.albums[0].title if track.albums else "Unknown Album"
        )
        duration_ms = track.duration_ms
        progress_ms = ynison["player_state"]["status"]["progress_ms"]
        
        logger.info(f"Now Playing: {title} by {artists} || {not ynison['player_state']['status']['paused']}")
        
        return {
            "title": title,
            "artists": artists,
            "album": album,
            "duration_ms": duration_ms,
            "progress_ms": progress_ms,
            "is_playing": not ynison["player_state"]["status"]["paused"],
            "track_id": track_id,
        }
        
    except Exception as e:
        error_msg = f"Error getting current track info: {e}"
        logger.error(error_msg, exc_info=True)
        await telegram_log(error_msg, topic_id=YM_THREAD, level="ERROR")
        return None

async def download_track(chat_id: int, track_url: Optional[str] = None):
                                 
    """Download track from Yandex Music.
    
    Downloads either the currently playing track or a track from a URL.
    
    Args:
        track_url: Yandex Music track URL (e.g., 
                   'https://music.yandex.ru/track/123456').
                   If None, downloads currently playing track.
        upload_to_telegram: Whether to upload to Telegram (default: True).
        chat_id: Telegram chat ID to upload to (required if uploading).
        
    Returns:
        Path to downloaded file or None if failed.
    """
    try:
        track_id = None
        
        # Extract track ID from URL if provided
        if track_url:
            import re
            track_match = re.search(r'track/(\d+)', track_url)
            if track_match:
                track_id = track_match.group(1)
                logger.info(f"Extracted track ID from URL: {track_id}")
            else:
                logger.error("Invalid track URL format")
                await telegram_log(
                    "Invalid track URL format",
                    topic_id=YM_THREAD,
                    level="ERROR"
                )
                return None
        else:
            # Get currently playing track
            track_info = await get_current_track_info()
            
            if not track_info or not track_info["is_playing"]:
                log_text = """No track is currently playing \n
                    Make sure you are playing YMusic on Android/iOS """
                logger.warning(log_text)
                await telegram_log(
                    log_text,
                    topic_id=YM_THREAD,
                    level="WARNING"
                )
                return None
            
            track_id = track_info["track_id"]
        
        # Initialize Yandex Music client
        client_ym = await ClientAsync(TOKEN).init()
        
        # Get track details
        track = (await client_ym.tracks([track_id]))[0]
        
        logger.info(f"Downloading: {track.title} by {track.artists[0].name}")
        await telegram_log(
            f"Downloading: {track.title} by {track.artists[0].name}",
            topic_id=YM_THREAD,
            level="INFO"
        )
        
        # Create download directory
        Path(DOWNLOAD_DIR).mkdir(exist_ok=True)
        
        # Get download info
        download_info = await track.get_download_info_async()
        if not download_info:
            logger.error("No download info available")
            return None
        
        # Get highest quality
        best_quality = sorted(
            download_info,
            key=lambda x: x.bitrate_in_kbps,
            reverse=True
        )[0]
        
        # Download track
        filename = f"{track.title} - {track.artists[0].name}.mp3"
        filename = "".join(
            c for c in filename
            if c.isalnum() or c in (' ', '-', '_', '.')
        )
        filepath = os.path.join(DOWNLOAD_DIR, filename)
        
        await best_quality.download_async(filepath)
        
        # Add metadata
        audio = MP3(filepath, ID3=ID3)
        
        # Initialize tags if they don't exist
        try:
            if audio.tags is None:
                audio.add_tags()
        except Exception:
            audio.add_tags()
        
        # Ensure tags are not None before adding
        if audio.tags is not None:
            audio.tags.add(TIT2(encoding=3, text=track.title))
            
            if track.artists:
                artists = ", ".join([
                    artist.name for artist in track.artists
                    if artist.name
                ])
                audio.tags.add(TPE1(encoding=3, text=artists))
            
            if track.albums and len(track.albums) > 0:
                audio.tags.add(TALB(encoding=3, text=track.albums[0].title))
        
        # Add cover art
        if track.cover_uri and audio.tags is not None:
            cover_url = f"https://{track.cover_uri.replace('%%', '400x400')}"
            async with ClientSession() as session:
                async with session.get(cover_url) as resp:
                    if resp.status == 200:
                        cover_data = await resp.read()
                        audio.tags.add(
                            APIC(
                                encoding=3,
                                mime='image/jpeg',
                                type=3,
                                desc='Cover',
                                data=cover_data
                            )
                        )
        
        audio.save()
        
        logger.info(f"Downloaded: {filename}")
        await telegram_log(
            f"Downloaded: {filename}",
            topic_id=YM_THREAD,
            level="INFO"
        )
        
        # Upload to Telegram 
        track_caption = (
            f"🎵 Title: **{track.title}**\n"
            f"👤 Artist: {', '.join([a.name for a in track.artists if a.name])}\n"
            f"💿 Album: {track.albums[0].title if track.albums else 'Unknown'}"
        )

        
        return filepath, track_caption
        
    except Exception as e:
        error_msg = f"Error downloading current track: {e}"
        logger.error(error_msg, exc_info=True)
        await telegram_log(
            error_msg,
            topic_id=YM_THREAD,
            level="ERROR"
        )
        return None


async def update_bio():
    """Fetch currently-playing track and update Telegram bio.
    
    Updates the Telegram bio based on the current Yandex Music playback state:
    
    - Playing: Update bio with track info (bot-managed).
    - Stopped: Restore user's original bio if bot had modified it.
    - First run: Save current bio as user's original bio.
    
    The function uses a special key (KEY constant) to identify
    bot-managed bios and distinguish them from user-set bios.
    """
    
    
    try:
        track_info = await get_current_track_info()
        
        if not track_info:
            logger.warning("Could not fetch track info")
            return
        
        me = await client_tg.get_me()
        current_bio = getattr(me, "about", "") or ""
        
        # Check if current bio is bot-managed (has the KEY)
        is_bot_managed = KEY in current_bio
        logger.debug(
            f"Current bio: '{current_bio}' | "
            f"Bot-managed: {is_bot_managed}"
        )
        
        # If bio doesn't have our KEY, it's user-managed - save it
        if not is_bot_managed and current_bio:
            bio_db.set_user_bio(current_bio)
            logger.info(f"Saved user bio: {current_bio[:50]}...")
            logger.debug("User bio saved to database.json")
        
        if track_info["is_playing"]:
            title = track_info["title"]
            artists = track_info["artists"]
            progress = ms_converter(track_info["progress_ms"])
            duration = ms_converter(track_info["duration_ms"])
            
            new_bio = ""
            for i, fmt in enumerate(BIOS):
                candidate = fmt.format(
                    title=title,
                    artists=artists,
                    progress=progress,
                    duration=duration
                )
                if len(candidate) <= LIMIT:
                    new_bio = candidate
                    logger.debug(
                        f"Bio format #{i+1} fits "
                        f"({len(candidate)}/{LIMIT} chars): {new_bio}"
                    )
                    break
                else:
                    logger.debug(
                        f"Bio format #{i+1} too long "
                        f"({len(candidate)}/{LIMIT} chars), trying next..."
                    )
            
            if new_bio and new_bio != current_bio:
                try:
                    await client_tg(UpdateProfileRequest(about=new_bio))
                    bio_db.set_bot_bio(new_bio)
                    info_msg = f"Bio updated: {new_bio}"
                    logger.info(info_msg)
                    await telegram_log(info_msg, topic_id=BIO_THREAD, level="INFO")
                except AboutTooLongError:
                    error_msg = "Bio exceeded Telegram length limit"
                    logger.error(error_msg)
                    await telegram_log(
                        error_msg,
                        topic_id=BIO_THREAD,
                        level="ERROR"
                    )
            elif not new_bio:
                warning_msg = (
                    "No bio format fits within the character limit"
                )
                logger.warning(warning_msg)
                await telegram_log(
                    warning_msg,
                    topic_id=BIO_THREAD,
                    level="WARNING"
                )
        else:
            # Not playing - restore user's original bio if bot had set one
            if is_bot_managed:
                user_bio = bio_db.get_user_bio()
                if user_bio != current_bio:
                    try:
                        await client_tg(UpdateProfileRequest(about=user_bio))
                        info_msg = f"Restored user bio: {user_bio}"
                        logger.info(info_msg)
                        await telegram_log(info_msg, topic_id=BIO_THREAD, level="INFO")
                    except AboutTooLongError:
                        error_msg = (
                            "User bio exceeded Telegram length limit"
                        )
                        logger.error(error_msg)
                        await telegram_log(
                            error_msg,
                            topic_id=YM_THREAD,
                            level="ERROR"
                        )
    
    except FloodWaitError as e:
        error_msg = f"Telegram flood wait: {e.seconds}s"
        logger.error(error_msg)
        await telegram_log(
            error_msg,
            topic_id=YM_THREAD,
            level="ERROR"
        )
        await asyncio.sleep(int(e.seconds))
    except Exception as e:
        error_msg = f"Error updating bio: {e}"
        logger.error(error_msg, exc_info=True)
        await telegram_log(
            error_msg,
            topic_id=YM_THREAD,
            level="ERROR"
        )


async def main():
    """Run bio sync loop continuously."""
    print('[*] Yandex Music Bio Sync is running... Press Ctrl+C to stop.')
    await telegram_log(
        "Yandex Music Bio Sync started",
        topic_id=YM_THREAD,
        level="INFO"
    )
    
    await client_tg.start()  # type: ignore
    
    # Run bio update loop
    while True:
        try:
            await update_bio()
            await asyncio.sleep(30)  # Update every 30 seconds
        except KeyboardInterrupt:
            print("\n[*] Stopping Yandex Music Bio Sync...")
            await telegram_log(
                "Yandex Music Bio Sync stopped",
                topic_id=YM_THREAD,
                level="INFO"
            )
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            await asyncio.sleep(10)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[*] Stopped by user")
