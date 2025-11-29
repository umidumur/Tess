"""Test script for emoji interactions via Telegram.

This script listens for trigger phrases and sends emoji interactions
to the sender with configurable repeat counts.
"""

import asyncio
import json
import os
import sys
import time
from random import choice

from dotenv import load_dotenv
from telethon.events import NewMessage
from telethon.tl.functions.messages import (
    GetStickerSetRequest,
    SetTypingRequest
)
from telethon.tl.types import (
    DataJSON,
    InputStickerSetAnimatedEmojiAnimations,
    SendMessageEmojiInteraction
)

# Ensure project root is on sys.path when running this file directly
sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from scripts.session_manager import get_client
from scripts.telegram_logger import telegram_log

load_dotenv()
client = get_client()

AUTO_REPLY_THREAD = int(os.getenv("AUTO_REPLY_THREAD", "0"))

async def send_emoji_interaction(
    event: NewMessage.Event,
    msgid,
    emoticon='❤️'
):
    """Send emoji interaction animation to a message.
    
    Args:
        event: The NewMessage event object.
        msgid: Message ID to send interaction to.
        emoticon: Emoji character to animate (default: '❤️').
    """
    interactions = []
    for i in range(2):
        if i == 0:
            interactions.append({'t': 0.0, 'i': 5})
        else:
            interactions.append({'t': 0.2, 'i': 5})
    
    interaction_json = {
        'v': 1,
        'a': interactions
    }

    try:
        await client(
            SetTypingRequest(
                peer=event.peer_id,
                top_msg_id=msgid,
                action=SendMessageEmojiInteraction(
                    emoticon=emoticon,
                    msg_id=msgid,
                    interaction=DataJSON(data=json.dumps(interaction_json))
                )
            )
        )
        print(f"Sent 5 taps for {emoticon}")
    except Exception as e:
        print(f"Error sending emoji interaction: {e}")


async def process_reply(event: NewMessage.Event):
    """Send a reply message with emoji.
    
    Args:
        event: The NewMessage event object.
        
    Returns:
        int: The ID of the sent message.
    """
    sent_message = await client.send_message(
        event.peer_id.user_id,
        message="❤️"
    )
    return sent_message.id


@client.on(NewMessage(incoming=True))
async def handle_message(event: NewMessage.Event):
    """Handle incoming private messages with trigger phrases.
    
    Args:
        event: The NewMessage event object.
    """
    if event.is_private:
        message_text = event.message.message
        trigger_phrases = ["test"]
        
        if any(phrase in message_text.lower() for phrase in trigger_phrases):
            user_id = event.sender_id
            
            # Parse repeat count from message (e.g., "test 5" -> 5)
            repeat_count = 1  # Default value
            parts = message_text.lower().split()
            for i, part in enumerate(parts):
                if part in trigger_phrases and i + 1 < len(parts):
                    try:
                        repeat_count = int(parts[i + 1])
                        break
                    except ValueError:
                        pass  # Keep default if not a valid number
            
            await client.get_dialogs()
            await telegram_log(
                f"Received test phrase: {message_text}",
                topic_id=AUTO_REPLY_THREAD,
                level="INFO"
            )
            user_link = f'[{user_id}](tg://openmessage?user_id={user_id})'
            await telegram_log(
                f'Triggering emoji for user ID {user_link} '
                f'with {repeat_count} repeats',
                topic_id=AUTO_REPLY_THREAD,
                level="INFO"
            )
            msgid = await process_reply(event)
            if msgid:
                for i in range(repeat_count):
                    await send_emoji_interaction(event, msgid)
                    await asyncio.sleep(0.5)


async def main():
    """Main entry point for the test script."""
    print('[*] Test script running... Press Ctrl+C to stop.')
    await telegram_log(
        "Test script started",
        topic_id=AUTO_REPLY_THREAD,
        level="INFO"
    )
    await client.start()  # type: ignore
    await client.run_until_disconnected()  # type: ignore


if __name__ == '__main__':
    asyncio.run(main())