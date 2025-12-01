"""Magic heart animation script for Telegram.

This module sends animated heart sequences in response to magic trigger
phrases in private messages. It includes cooldown protection to prevent abuse.
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
    SendReactionRequest,
    SetTypingRequest
)
from telethon.tl.types import (
    DataJSON,
    ReactionEmoji,
    SendMessageEmojiInteraction
)

# Ensure project root is on sys.path when running this file directly so
# `from scripts.*` imports work regardless of how the script is executed.
sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from scripts.session_manager import get_client
from scripts.telegram_logger import telegram_log, validate_bot_config

load_dotenv()

# Constants
HEART = '🤍'
HEARTS = [
    '🤎', '🧡', '💙', '🖤', '💛', '💜', '❤️‍🔥',
    '💚', '❤️‍🩹', '💖', '❤'
]
COLORED_HEARTS = ['❤', '💚', '💙', '💜', '❤️‍🩹', '❤️‍🔥', '💖', '💝']
ANIMATED_HEARTS = [
    '🩷', '🧡', '💚', '💛', '🩵', '💜', '💙', '🤎', '🤍', '❤️'
]
MAGIC_PHRASES = ['magic', 'ily']
EDIT_DELAY = 0.20

AUTO_REPLY_THREAD = int(os.getenv("AUTO_REPLY_THREAD", "0"))

PARADE_MAP = '''
000000000
001101100
011111110
011111110
011111110
001111100
000111000
000010000
000000000
'''

# END_MAP for the end animation (define maps)
END_MAP = [
'''
000000000
001101100
010010010
010000010
010000010
001000100
000101000
000010000
000000000
''',
'''
111111111
110010011
101101101
101111101
101111101
110111011
111010111
111101111
111111111
'''
]


client = get_client("MagicHeart")


def generate_parade_colored():
    """Generate colored heart parade grid.
    
    Returns:
        String containing grid of randomly colored hearts.
    """
    output = ''
    for c in PARADE_MAP:
        if c == '0':
            output += HEART
        elif c == '1':
            output += choice(COLORED_HEARTS)
        else:
            output += c
    return output


def generate_parade_hearts(num):
    """Generate heart parade grid with specific heart type.
    
    Args:
        num: Index of heart type from HEARTS list.
        
    Returns:
        String containing grid with specified heart type.
    """
    output = ''
    for c in PARADE_MAP:
        if c == '0':
            output += HEART
        elif c == '1':
            output += HEARTS[num]
        else:
            output += c
    return output


def generate_end(num1, num2):
    """Generate end animation grid.
    
    Args:
        num1: Index of END_MAP to use.
        num2: Index of heart type from HEARTS list.
        
    Returns:
        String containing grid for end animation.
    """
    output = ''
    for c in END_MAP[num1]:
        if c == '0':
            output += HEART
        elif c == '1':
            output += HEARTS[num2]
        else:
            output += c
    return output


async def process_love_words(event: NewMessage.Event, msgid):
    """Animate 'I love you' text message.
    
    Args:
        event: Telegram NewMessage event.
        msgid: Message ID to edit.
    """
    await client.edit_message(event.peer_id.user_id, msgid, 'i')
    await asyncio.sleep(1/2)
    await client.edit_message(
        event.peer_id.user_id,
        msgid,
        'i love'
    )
    await asyncio.sleep(1/2)
    await client.edit_message(
        event.peer_id.user_id,
        msgid,
        'i love you'
    )
    await asyncio.sleep(1/2)
    await client.edit_message(
        event.peer_id.user_id,
        msgid,
        'i love you forever'
    )
    await asyncio.sleep(1/2)
    await client.edit_message(
        event.peer_id.user_id,
        msgid,
        'i love you forever❤️‍🩹'
    )
    await asyncio.sleep(2)


async def process_hearts_carusel(event: NewMessage.Event, msgid):
    """Animate cycling through animated hearts.
    
    Args:
        event: Telegram NewMessage event.
        msgid: Message ID to edit.
    """
    for i in range(0, ANIMATED_HEARTS.__len__(), 1):
        await client.edit_message(
            event.peer_id.user_id,
            msgid,
            ANIMATED_HEARTS[i]
        )
        await asyncio.sleep(3)


async def send_emoji_reaction(event: NewMessage.Event, msgid, emoticon='❤️'):
    """Send emoji reaction to a message.
    
    Args:
        event: Telegram NewMessage event.
        msgid: Message ID to react to.
        emoticon: Emoji to send as reaction (default: ❤️).
    """
    try:
        await client(SendReactionRequest(
            peer=event.peer_id,
            msg_id=msgid,
            reaction=[ReactionEmoji(emoticon=emoticon)]
        ))
        await telegram_log(
            f"Reaction {emoticon} sent successfully",
            topic_id=AUTO_REPLY_THREAD,
            level="DEBUG"
        )
    except Exception as e:
        await telegram_log(
            f"Error sending emoji reaction: {e}",
            topic_id=AUTO_REPLY_THREAD,
            level="ERROR"
        )


async def send_emoji_interaction(event: NewMessage.Event, msgid,
                                 emoticon='❤️'):
    """Send emoji interaction to a message.
    
    Args:
        event: Telegram NewMessage event.
        msgid: Message ID to interact with.
        emoticon: Emoji to send as interaction (default: ❤️).
    """
    interactions = []
    # Adjust the number of taps here (more than 2 may not register)
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
        await client(SetTypingRequest(
            peer=event.peer_id,
            top_msg_id=msgid,
            action=SendMessageEmojiInteraction(
                emoticon=emoticon,
                msg_id=msgid,
                interaction=DataJSON(data=json.dumps(interaction_json))
            )
        ))
    except Exception as e:
        await telegram_log(
            f"Error sending emoji interaction: {e}",
            topic_id=AUTO_REPLY_THREAD,
            level="ERROR"
        )


async def process_build_place(event: NewMessage.Event, msgid):
    """Build heart grid animation.
    
    Args:
        event: Telegram NewMessage event.
        msgid: Message ID to edit.
    """
    output = HEART
    for i in range(8):
        output += HEART
        await client.edit_message(event.peer_id.user_id, msgid, output)
        await asyncio.sleep(EDIT_DELAY)
    for i in range(8):
        output += '\n'
        output += 9*HEART
        await client.edit_message(event.peer_id.user_id, msgid, output)
        await asyncio.sleep(EDIT_DELAY)


async def process_colored_heart(event: NewMessage.Event, msgid):
    """Animate colored heart grid.
    
    Args:
        event: Telegram NewMessage event.
        msgid: Message ID to edit.
    """
    output = ''
    for i in range(11):
        text = generate_parade_hearts(i)
        await client.edit_message(event.peer_id.user_id, msgid, text)
        await asyncio.sleep(EDIT_DELAY)


async def process_preend(event: NewMessage.Event, msgid):
    """Show final heart grid before end animation.
    
    Args:
        event: Telegram NewMessage event.
        msgid: Message ID to edit.
    """
    output = ''
    text = generate_parade_hearts(10)
    await client.edit_message(event.peer_id.user_id, msgid, text)
    await asyncio.sleep(EDIT_DELAY)


async def process_colored_parade(event: NewMessage.Event, msgid):
    """Animate randomly colored heart parade.
    
    Args:
        event: Telegram NewMessage event.
        msgid: Message ID to edit.
    """
    for i in range(15):
        text = generate_parade_colored()
        await client.edit_message(event.peer_id.user_id, msgid, text)
        await asyncio.sleep(2*EDIT_DELAY)


async def process_end(event: NewMessage.Event, msgid):
    """Animate end sequence.
    
    Args:
        event: Telegram NewMessage event.
        msgid: Message ID to edit.
    """
    for i in range(11):
        for c in range(2):
            text = generate_end(c, i)
            await client.edit_message(event.peer_id.user_id, msgid, text)
            await asyncio.sleep(EDIT_DELAY)


async def process_destroy_place(event: NewMessage.Event, msgid):
    """Destroy heart grid animation by removing rows and columns.
    
    Args:
        event: Telegram NewMessage event.
        msgid: Message ID to edit.
    """
    try:
        messages = await client.get_messages(event.chat_id, limit=1)
        if messages:
            msg = messages if not isinstance(messages, list) else messages[0]
            output = msg.message or ""
            if output:
                arr = output.split('\n')
                while len(arr) > 0:
                    # Remove first row
                    if arr:
                        arr.pop(0)
                    
                    # Remove last character from each remaining row
                    for i in range(len(arr)):
                        if arr[i]:  # Check that string is not empty
                            arr[i] = arr[i][:-1]
                    
                    # Update message
                    temp = '\n'.join(arr)
                    await client.edit_message(
                        event.peer_id.user_id,
                        msgid,
                        temp
                    )
                    await asyncio.sleep(EDIT_DELAY)
                
    except Exception as e:
        print(f"Error in process_destroy_place: {e}")


async def process_reply(event: NewMessage.Event):
    """Send initial heart message and get its ID.
    
    Args:
        event: Telegram NewMessage event.
        
    Returns:
        Message ID of sent message, or None if failed.
    """
    await client.send_message(event.peer_id.user_id, message=HEART, reply_to=event.message.id)
    messages = await client.get_messages(event.chat_id, limit=1)
    if messages:
        msg = messages if not isinstance(messages, list) else messages[0]
        msgid = msg.id
        return msgid
    return None


# Global dictionary to store last trigger time for each user
last_triggered_time = {}

@client.on(NewMessage(incoming=True))
async def handle_message(event: NewMessage.Event):
    """Handle incoming messages for magic phrases.
    
    Checks for trigger phrases in private messages and executes the magic
    heart animation sequence with 60-second cooldown per sender to prevent
    abuse.
    
    Args:
        event: Telegram NewMessage event.
    """
    if event.is_private:
        # Check if 60 seconds have passed since last trigger for this user
        current_time = time.time()
        user_id = event.sender_id
        origin_msgid = event.message.id  # Save original message ID

        
        # Check for magic phrase in message
        message_text = event.message.message
        
        if any(phrase in message_text for phrase in MAGIC_PHRASES):
            
            if user_id in last_triggered_time:
                elapsed_time = current_time - last_triggered_time[user_id]
                if elapsed_time < 300:
                    # If less than 5 minutes, ignore the message
                    await telegram_log(
                        f'Ignoring abuse message from user ID '
                        f'[{user_id}](tg://openmessage?user_id={user_id})',
                        topic_id=AUTO_REPLY_THREAD,
                        level="WARNING"
                    )
                    return
            
            
            # Update last trigger time
            last_triggered_time[user_id] = current_time

            await client.get_dialogs()
            await telegram_log(
                f"Received magic phrase: {message_text}",
                topic_id=AUTO_REPLY_THREAD,
                level="INFO"
            )
            await telegram_log(
                f'Triggering magic heart for user ID '
                f'[{user_id}](tg://openmessage?user_id={user_id})',
                topic_id=AUTO_REPLY_THREAD,
                level="INFO"
            )
            msgid = await process_reply(event)
            if msgid:
                await process_build_place(event, msgid)
                await telegram_log(
                    "1️⃣ Phase process\\_build\\_place successfully "
                    "completed.",
                    topic_id=AUTO_REPLY_THREAD,
                    level="DEBUG"
                )
                await process_colored_heart(event, msgid)
                await telegram_log(
                    "2️⃣ Phase process\\_colored\\_heart successfully "
                    "completed.",
                    topic_id=AUTO_REPLY_THREAD,
                    level="DEBUG"
                )
                await process_colored_parade(event, msgid)
                await telegram_log(
                    "3️⃣ Phase process\\_colored\\_parade successfully "
                    "completed.",
                    topic_id=AUTO_REPLY_THREAD,
                    level="DEBUG"
                )
                await process_preend(event, msgid)
                await telegram_log(
                    "4️⃣ Phase process\\_preend successfully completed.",
                    topic_id=AUTO_REPLY_THREAD,
                    level="DEBUG"
                )
                await process_end(event, msgid)
                await telegram_log(
                    "5️⃣ Phase process\\_end successfully completed.",
                    topic_id=AUTO_REPLY_THREAD,
                    level="DEBUG"
                )
                await process_destroy_place(event, msgid)
                await telegram_log(
                    "6️⃣ Phase process\\_destroy\\_place successfully "
                    "completed.",
                    topic_id=AUTO_REPLY_THREAD,
                    level="DEBUG"
                )
                await process_love_words(event, msgid)
                await telegram_log(
                    "7️⃣ Phase process\\_love\\_words successfully "
                    "completed.",
                    topic_id=AUTO_REPLY_THREAD,
                    level="DEBUG"
                )
                await process_hearts_carusel(event, msgid)
                await telegram_log(
                    "8️⃣ Phase process\\_hearts\\_carusel successfully "
                    "completed.",
                    topic_id=AUTO_REPLY_THREAD,
                    level="DEBUG"
                )
                for i in range(50):
                    await send_emoji_interaction(event, msgid)
                    await asyncio.sleep(0.5)
                await telegram_log(
                    "9️⃣ Emoji interaction successfully completed.",
                    topic_id=AUTO_REPLY_THREAD,
                    level="DEBUG"
                )
                await send_emoji_reaction(event, origin_msgid)
                # await telegram_log(
                #     "🔟 Emoji reaction successfully completed.",
                #     topic_id=AUTO_REPLY_THREAD,
                #     level="DEBUG"
                # )
            # Clear user entry after all processes complete
            if user_id in last_triggered_time:
                del last_triggered_time[user_id]
            
            await telegram_log(
                f'✅ Completed magic heart sequence for user ID '
                f'[{user_id}](tg://openmessage?user_id={user_id})',
                topic_id=AUTO_REPLY_THREAD,
                level="INFO"
            )


async def main():
    """Start magic heart auto-reply bot."""
    print('[*] Magic Heart Auto-Reply is running... Press Ctrl+C to stop.')
    await telegram_log(
        "Magic Heart Auto-Reply started",
        topic_id=AUTO_REPLY_THREAD,
        level="INFO"
    )
    await client.start()  # type: ignore
    await client.run_until_disconnected()  # type: ignore


if __name__ == '__main__':
    # Fail fast if bot configuration is missing
    if not validate_bot_config(require_chat=True):
        print("Missing BOT_TOKEN or TELEGRAM_CHAT_ID. Aborting.")
        sys.exit(1)

    asyncio.run(main())





























