"""Telegram logger for sending messages via Bot API.

This module provides async functions to send log messages to Telegram groups
or topics using the Telegram Bot API with Markdown formatting.
"""

import asyncio
import logging
import os
from typing import Optional, Union

import aiohttp
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Emoji mapping for log levels
LOG_LEVEL_EMOJIS = {
    "DEBUG": "🔍",
    "INFO": "ℹ️",
    "WARNING": "⚠️",
    "ERROR": "❌",
}


async def telegram_log(
    message: str,
    chat_id: Optional[Union[str, int]] = None,
    topic_id: Optional[int] = None,
    level: str = "INFO"
) -> bool:
    """Send a log message to a Telegram group or topic via Bot API.
    
    Args:
        message: The log message to send.
        chat_id: Telegram chat/group ID (uses TELEGRAM_CHAT_ID env var if not provided).
        topic_id: Optional topic ID for topics in a group (or thread ID).
        level: Log level (INFO, WARNING, ERROR, DEBUG).
    
    Returns:
        True if sent successfully, False otherwise.
    """
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.error("BOT_TOKEN not set in environment")
        return False
    
    if not chat_id:
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not chat_id:
        logger.error("chat_id not provided and TELEGRAM_CHAT_ID not set in environment")
        return False
    # Normalize chat_id: try to convert numeric strings to int
    try:
        if isinstance(chat_id, str) and chat_id.lstrip("-").isdigit():
            chat_id = int(chat_id)
    except Exception:
        # keep original chat_id if conversion fails
        pass

    # Format message with level prefix and emoji
    emoji = LOG_LEVEL_EMOJIS.get(level.upper(), "📝")
    # Markdown (v1) uses simple formatting: *bold*, _italic_, `code`
    formatted_message = f"{emoji} *[{level}]* - {message}"

    # Build the API endpoint
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": formatted_message,
        "parse_mode": "Markdown"
    }

    # Add topic_id if provided (for topics in groups) and valid (>0)
    if topic_id is not None:
        try:
            tid = int(topic_id)
            if tid > 0:
                payload["message_thread_id"] = tid
        except Exception:
            logger.debug(
                "Invalid topic_id provided to telegram_log: %r",
                topic_id
            )
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                text = await response.text()
                if response.status == 200:
                    logger.info("Log sent to Telegram: %s", message)
                    return True
                else:
                    # Log payload and response for debugging 400 errors
                    try:
                        resp_json = await response.json()
                    except Exception:
                        resp_json = None
                    logger.error(
                        "Failed to send log to Telegram: %s - "
                        "status=%s payload=%r response_text=%s "
                        "response_json=%r",
                        message,
                        response.status,
                        payload,
                        text,
                        resp_json,
                    )
                    return False
    except Exception as e:
        logger.error(f"Error sending log to Telegram: {e}")
        return False


def telegram_log_sync(
    message: str,
    chat_id: Optional[Union[str, int]] = None,
    topic_id: Optional[int] = None,
    level: str = "INFO"
) -> bool:
    """Synchronous wrapper for telegram_log.
    
    Use this if you're not in an async context. Creates or uses existing
    event loop to run the async function.
    
    Args:
        message: The log message to send.
        chat_id: Telegram chat/group ID.
        topic_id: Optional topic ID.
        level: Log level (INFO, WARNING, ERROR, DEBUG).
        
    Returns:
        True if sent successfully, False otherwise.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already in async context, return False and log warning
            logger.warning(
                "Cannot use sync wrapper in async context. "
                "Use telegram_log() instead."
            )
            return False
        return loop.run_until_complete(
            telegram_log(message, chat_id, topic_id, level)
        )
    except RuntimeError:
        # No event loop, create a new one
        return asyncio.run(
            telegram_log(message, chat_id, topic_id, level)
        )


def validate_bot_config(require_chat: bool = True) -> bool:
    """Validate BOT_TOKEN and optionally TELEGRAM_CHAT_ID presence.
    
    This helper is intended to be called at startup so scripts can fail
    fast with a clear message instead of attempting to call the API.
    
    Args:
        require_chat: Whether to require TELEGRAM_CHAT_ID (default: True).
        
    Returns:
        True if required configuration is present, False otherwise.
    """
    bot_token = os.getenv("BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    ok = True
    if not bot_token:
        logger.error(
            "BOT_TOKEN environment variable is not set. "
            "Set BOT_TOKEN in your .env or environment."
        )
        ok = False
    if require_chat and not chat:
        logger.error(
            "TELEGRAM_CHAT_ID environment variable is not set. "
            "Set TELEGRAM_CHAT_ID in your .env or environment."
        )
        ok = False
    return ok


__all__ = ["telegram_log", "telegram_log_sync", "validate_bot_config"]

