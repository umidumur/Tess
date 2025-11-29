"""Helper to create and reuse a Telethon TelegramClient instance.

Reads configuration from environment variables (via python-dotenv if present).
Uses connection caching to reuse connections and avoid SQLite locking issues.

Features:
- Single global cached connection per session
- Automatic connection reuse
- Thread-safe caching
- Connection validation
"""

import os
import threading
from typing import Dict, Optional

from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv()

# Connection cache: session_name -> client instance
_client_cache: Dict[str, TelegramClient] = {}
_cache_lock = threading.Lock()


def get_client(session_name: Optional[str] = None) -> TelegramClient:
    """Get or create a cached Telegram client instance.
    
    This function implements connection caching to reuse existing connections
    instead of creating new ones each time. This prevents SQLite locking issues
    and improves performance.
    
    Args:
        session_name: Name of the session file (without .session extension).
                     If None, uses "Tess2" as default.
    
    Returns:
        Cached TelegramClient instance.
    
    Raises:
        RuntimeError: If API_ID or API_HASH are not set.
    
    Example:
        client = get_client()
        client.send_message("username", "Hello")
        # Next call reuses the same connection
        client2 = get_client()
        # client2 is the same object as client
    """
    global _client_cache
    
    # Use default session name if not provided
    if session_name is None:
        session_name = "Tess2"
    
    # Allow overriding the session name from the environment for subprocesses
    env_session = os.getenv("SESSION_NAME")
    if env_session:
        session_name = env_session

    with _cache_lock:
        # Check if client already exists in cache
        if session_name in _client_cache:
            cached_client = _client_cache[session_name]
            # Validate that cached client is still usable
            if _is_valid_client(cached_client):
                return cached_client
            else:
                # Remove invalid client from cache
                del _client_cache[session_name]
        
        # Create new client and cache it
        api_id = os.getenv("API_ID")
        api_hash = os.getenv("API_HASH")
        
        if not api_id or not api_hash:
            raise RuntimeError(
                "API_ID and API_HASH must be set in environment "
                "or .env file"
            )
        
        # Create and cache new client
        client = TelegramClient(session_name, int(api_id), api_hash)
        _client_cache[session_name] = client
        
        return client


def _is_valid_client(client: TelegramClient) -> bool:
    """Check if a cached client is still valid and usable.
    
    Args:
        client: TelegramClient instance to validate.
    
    Returns:
        True if client is valid, False otherwise.
    """
    try:
        # Check if client object exists and has required attributes
        return client is not None and hasattr(client, '_sender')
    except:
        return False


def clear_cache(session_name: Optional[str] = None) -> None:
    """Clear cached connections.
    
    Args:
        session_name: Specific session to clear. If None, clears all.
    
    Example:
        # Clear specific session
        clear_cache("Tess2")
        
        # Clear all cached connections
        clear_cache()
    """
    global _client_cache
    
    with _cache_lock:
        if session_name is None:
            # Clear all connections
            for name, client in _client_cache.items():
                _disconnect_client(client)
            _client_cache.clear()
        else:
            # Clear specific connection
            if session_name in _client_cache:
                _disconnect_client(_client_cache[session_name])
                del _client_cache[session_name]


def _disconnect_client(client: TelegramClient) -> None:
    """Safely disconnect a client.
    
    Args:
        client: TelegramClient instance to disconnect.
    """
    try:
        if client and client.is_connected():
            client.disconnect()
    except:
        pass


def get_cache_info() -> Dict[str, str]:
    """Get information about cached connections.
    
    Returns:
        Dictionary with session names as keys and connection status as values.
    
    Example:
        info = get_cache_info()
        # {'Tess2': 'cached'}
    """
    with _cache_lock:
        return {
            session_name: "cached"
            for session_name in _client_cache.keys()
        }


def close_all() -> None:
    """Close all cached connections. Call this during shutdown.
    
    Example:
        import atexit
        atexit.register(close_all)
    """
    clear_cache()


__all__ = ["get_client", "clear_cache", "get_cache_info", "close_all"]