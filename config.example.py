"""Configuration example file for Telegram automation.

Copy this file to `.env` or set environment variables directly.

Example `.env` lines:
    API_ID=123456
    API_HASH=your_api_hash_here
    BOT_TOKEN=optional_bot_token_if_using_a_bot

Note:
    For local use it's often easier to create a `.env` file with the
    variables above and use python-dotenv to load them at runtime.
"""

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

API_ID = "YOUR_API_ID"
API_HASH = "YOUR_API_HASH"
BOT_TOKEN = "OPTIONAL_BOT_TOKEN"
