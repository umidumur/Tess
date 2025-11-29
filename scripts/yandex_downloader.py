"""Yandex Music downloader and Telegram uploader.

This script downloads tracks from Yandex Music and uploads them to Telegram.
Supports track search, download, and upload with metadata.
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB
from telethon import events
from yandex_music import ClientAsync

# Add parent directory to path for imports
sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from scripts.session_manager import get_client
from scripts.telegram_logger import telegram_log, validate_bot_config

load_dotenv()

# Environment variables
YANDEX_TOKEN = os.getenv("YANDEX_MUSIC_AUTH_TOKEN")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads")
MUSIC_THREAD = int(os.getenv("MUSIC_THREAD", "0"))

# Telegram client
client = get_client()


async def search_track(ya_client: ClientAsync, query: str, limit: int = 5):
    """Search for tracks on Yandex Music.
    
    Args:
        ya_client: Yandex Music client instance.
        query: Search query string.
        limit: Maximum number of results (default: 5).
        
    Returns:
        List of track search results.
    """
    try:
        search_result = await ya_client.search(query, type_='track')
        if search_result.tracks:
            return search_result.tracks.results[:limit]
        return []
    except Exception as e:
        await telegram_log(
            f"Error searching tracks: {e}",
            topic_id=MUSIC_THREAD,
            level="ERROR"
        )
        return []


async def download_track(ya_client: ClientAsync, track_id: str,
                        download_path: str):
    """Download track from Yandex Music.
    
    Args:
        ya_client: Yandex Music client instance.
        track_id: Yandex Music track ID.
        download_path: Path to save the downloaded file.
        
    Returns:
        Path to downloaded file or None if failed.
    """
    try:
        track = await ya_client.tracks([track_id])
        if not track or len(track) == 0:
            await telegram_log(
                f"Track {track_id} not found",
                topic_id=MUSIC_THREAD,
                level="ERROR"
            )
            return None
        
        track = track[0]
        
        # Get download info
        download_info = await track.get_download_info_async()
        if not download_info:
            await telegram_log(
                "No download info available",
                topic_id=MUSIC_THREAD,
                level="ERROR"
            )
            return None
        
        # Get highest quality available
        best_quality = sorted(
            download_info,
            key=lambda x: x.bitrate_in_kbps,
            reverse=True
        )[0]
        
        # Download track
        filename = f"{track.title} - {track.artists[0].name}.mp3"
        filename = "".join(
            c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')
        )
        filepath = os.path.join(download_path, filename)
        
        await best_quality.download_async(filepath)
        
        # Add metadata
        await add_metadata(filepath, track)
        
        await telegram_log(
            f"Downloaded: {filename}",
            topic_id=MUSIC_THREAD,
            level="INFO"
        )
        
        return filepath
        
    except Exception as e:
        await telegram_log(
            f"Error downloading track: {e}",
            topic_id=MUSIC_THREAD,
            level="ERROR"
        )
        return None


async def add_metadata(filepath: str, track):
    """Add metadata to MP3 file.
    
    Args:
        filepath: Path to MP3 file.
        track: Yandex Music track object.
    """
    try:
        audio = MP3(filepath, ID3=ID3)
        
        # Add tags
        audio.tags.add(TIT2(encoding=3, text=track.title))
        
        if track.artists:
            artists = ", ".join([artist.name for artist in track.artists])
            audio.tags.add(TPE1(encoding=3, text=artists))
        
        if track.albums and len(track.albums) > 0:
            audio.tags.add(TALB(encoding=3, text=track.albums[0].title))
        
        # Add cover art
        if track.cover_uri:
            cover_url = f"https://{track.cover_uri.replace('%%', '400x400')}"
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
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
            except Exception as e:
                await telegram_log(
                    f"Failed to add cover art: {e}",
                    topic_id=MUSIC_THREAD,
                    level="WARNING"
                )
        
        audio.save()
        
    except Exception as e:
        await telegram_log(
            f"Error adding metadata: {e}",
            topic_id=MUSIC_THREAD,
            level="WARNING"
        )


async def upload_to_telegram(filepath: str, chat_id, caption: str = ""):
    """Upload audio file to Telegram.
    
    Args:
        filepath: Path to audio file.
        chat_id: Telegram chat ID to upload to.
        caption: Optional caption for the file.
        
    Returns:
        True if successful, False otherwise.
    """
    try:
        await client.send_file(
            chat_id,
            filepath,
            caption=caption,
            attributes=[],
            force_document=False
        )
        
        await telegram_log(
            f"Uploaded to Telegram: {os.path.basename(filepath)}",
            topic_id=MUSIC_THREAD,
            level="INFO"
        )
        
        return True
        
    except Exception as e:
        await telegram_log(
            f"Error uploading to Telegram: {e}",
            topic_id=MUSIC_THREAD,
            level="ERROR"
        )
        return False


@client.on(events.NewMessage(outgoing=True, pattern=r'^/dl (.+)'))
async def handle_download_command(event):
    """Handle /dl command to download and upload music.
    
    Usage: /dl <track name or URL>
    """
    query = event.pattern_match.group(1)
    
    await event.reply(f"🔍 Searching for: {query}")
    
    try:
        # Initialize Yandex Music client
        ya_client = await ClientAsync(YANDEX_TOKEN).init()
        
        # Create download directory
        Path(DOWNLOAD_DIR).mkdir(exist_ok=True)
        
        # Search for tracks
        tracks = await search_track(ya_client, query, limit=1)
        
        if not tracks:
            await event.reply("❌ No tracks found")
            return
        
        track = tracks[0]
        track_info = (
            f"📀 **{track.title}**\n"
            f"👤 {', '.join([a.name for a in track.artists])}\n"
            f"💿 {track.albums[0].title if track.albums else 'Unknown'}"
        )
        
        await event.reply(f"⬇️ Downloading...\n\n{track_info}")
        
        # Download track
        filepath = await download_track(
            ya_client,
            track.id,
            DOWNLOAD_DIR
        )
        
        if not filepath:
            await event.reply("❌ Download failed")
            return
        
        await event.reply("⬆️ Uploading to Telegram...")
        
        # Upload to Telegram
        success = await upload_to_telegram(
            filepath,
            event.chat_id,
            caption=track_info
        )
        
        if success:
            await event.reply("✅ Done!")
        else:
            await event.reply("❌ Upload failed")
        
        # Cleanup
        try:
            os.remove(filepath)
        except Exception:
            pass
            
    except Exception as e:
        await event.reply(f"❌ Error: {e}")
        await telegram_log(
            f"Error in download command: {e}",
            topic_id=MUSIC_THREAD,
            level="ERROR"
        )


@client.on(events.NewMessage(outgoing=True, pattern=r'^/search (.+)'))
async def handle_search_command(event):
    """Handle /search command to find tracks.
    
    Usage: /search <track name>
    """
    query = event.pattern_match.group(1)
    
    try:
        ya_client = await ClientAsync(YANDEX_TOKEN).init()
        tracks = await search_track(ya_client, query, limit=5)
        
        if not tracks:
            await event.reply("❌ No tracks found")
            return
        
        result_lines = ["🔍 **Search Results:**\n"]
        for i, track in enumerate(tracks, 1):
            artists = ', '.join([a.name for a in track.artists])
            album = track.albums[0].title if track.albums else 'Unknown'
            result_lines.append(
                f"{i}. **{track.title}**\n"
                f"   👤 {artists}\n"
                f"   💿 {album}\n"
                f"   🆔 `{track.id}`\n"
            )
        
        await event.reply('\n'.join(result_lines))
        
    except Exception as e:
        await event.reply(f"❌ Error: {e}")
        await telegram_log(
            f"Error in search command: {e}",
            topic_id=MUSIC_THREAD,
            level="ERROR"
        )


async def main():
    """Start Yandex Music downloader bot."""
    print('[*] Yandex Music Downloader is running... Press Ctrl+C to stop.')
    await telegram_log(
        "Yandex Music Downloader started",
        topic_id=MUSIC_THREAD,
        level="INFO"
    )
    await client.start()  # type: ignore
    await client.run_until_disconnected()  # type: ignore


if __name__ == '__main__':
    # Validate configuration
    if not YANDEX_TOKEN:
        print("Missing YANDEX_MUSIC_AUTH_TOKEN. Aborting.")
        sys.exit(1)
    
    if not validate_bot_config(require_chat=False):
        print("Warning: BOT_TOKEN not set, logging disabled.")
    
    asyncio.run(main())
