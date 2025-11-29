# Tess Telegram Automation Suite

Tess is a collection of Telethon-based automation scripts for enhancing a Telegram account or bot with Yandex Music integration, reactive emoji animations, profile bio synchronization, and remote logging.

## Features
- Bio Sync: Periodically updates your Telegram bio with the currently playing Yandex Music track.
- Track Downloader: Download Yandex Music tracks (by URL or search query) with embedded metadata and cover art.
- Link Auto-Detection: Automatically detects Yandex Music track links in outgoing messages and uploads the track.
- Heart Animation: Reactive multi-phase emoji heart animation for private trigger phrases.
- Session Management: Reuses a cached Telethon client to avoid redundant logins (`scripts/session_manager.py`).
- Remote Telegram Logging: Sends structured log messages (severity + emoji) to a specified chat (`scripts/telegram_logger.py`).
- Command Control: Start/stop feature processes from a central controller (`main.py`).
- Clean File Lifecycle: Downloads stored in `downloads/` and removed after successful upload.

## Repository Structure
```
README.md
requirements.txt
main.py                # Central command controller
config.example.py      # Example config placeholder
scripts/
  yandex_sync.py       # Bio sync + universal track downloader
  yandex_downloader.py # Standalone search/download/upload commands
  magic_heart.py       # Emoji heart animation logic
  session_manager.py   # Cached TelegramClient management
  telegram_logger.py   # Remote logging utilities
downloads/             # Temporary downloaded audio files
```

## Environment Variables
Create a `.env` file (excluded via `.gitignore`) with:
```
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
BOT_TOKEN=your_bot_token              # If using bot-specific actions
TELEGRAM_CHAT_ID=123456789            # Chat ID for logging / uploads
YANDEX_MUSIC_AUTH_TOKEN=your_auth_token  # Yandex Music auth (cookies / token)
```
Obtain Yandex auth token using your browser session or official API instructions.

## Installation
```powershell
# Clone and enter directory
git clone <repo-url> Tess
cd Tess

# (Optional) Create virtual environment
python -m venv .venv
./.venv/Scripts/Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

## Running Scripts
### Central Controller
`main.py` manages starting/stopping feature scripts and handles outgoing message link detection.
```powershell
python main.py
```

### Bio Sync Standalone
Runs continuous bio synchronization loop:
```powershell
python scripts/yandex_sync.py
```

### Yandex Downloader Bot
Provides `/dl` and `/search` commands:
```powershell
python scripts/yandex_downloader.py
```

## Commands (main.py)
- `/start_auto_reply` : Launches heart animation process.
- `/stop_auto_reply`  : Stops heart animation process.
- `/start_ym_sync`    : Starts Yandex Music bio sync process.
- `/stop_ym_sync`     : Stops Yandex Music bio sync process.
- `/status`           : Shows which processes are running.
- `/help`             : Lists available commands.

Outgoing messages containing a Yandex Music track URL trigger automatic download + upload (with metadata) and then file deletion.

## Commands (yandex_downloader.py)
- `/search <query>` : Returns a list of matching tracks.
- `/dl <query|url>` : Downloads best match or specific URL, embeds tags & cover art, uploads, then deletes local file.

## Universal Track Download
`scripts/yandex_sync.py` exposes `download_current_track(track_url=None)`:
- If `track_url` provided: downloads that track.
- Else: uses current playing track via Ynison WebSocket.
Returns `(file_path, caption)` for upload handling.

## Metadata & Tagging
Mutagen is used to embed:
- Title (TIT2)
- Artist (TPE1)
- Album (TALB)
- Cover art (APIC) when available

## Logging
Use `telegram_logger.telegram_log(level, message)` for remote reporting. Ensure `BOT_TOKEN` and `TELEGRAM_CHAT_ID` are configured.

## Development Notes
- `.gitignore` excludes sessions, logs, downloads, and broad `*.json` files. Remove `*.json` if you need to version structured data like `database.json`.
- Duplicate Yandex logic in `yandex_sync.py` and `yandex_downloader.py` can be refactored into a shared helper later (e.g., `scripts/yandex_utils.py`).
- Upload action feedback currently sends a typing/upload indication; progress granularity can be improved with repeated action requests.

## Troubleshooting
- Exit Code 1 when running `main.py`: Check environment variables and session files.
- Missing metadata: Verify `mutagen` installed and track cover URL reachable.
- No bio updates: Confirm `YANDEX_MUSIC_AUTH_TOKEN` validity and active playback.

## Future Improvements (Ideas)
- Centralize Yandex track utilities.
- Incremental upload progress simulation.
- Add unit tests for metadata tagging.
- Optional caching of cover art.

## License
This project is licensed under the MIT License. See the `LICENSE` file for full text.

## Disclaimer
Use responsibly; automated actions may be subject to Telegram rate limits.

---
Feel free to open issues or suggest enhancements.
