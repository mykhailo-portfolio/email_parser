"""
Redis-based key-value storage for pointer management.

Provides persistent storage for Gmail pointer state across restarts.
"""

from __future__ import annotations
from typing import Optional
import redis
from app.storage.local_state import PointerStorage
from app.logging import logger


class RedisKVStorage:
    """
    Redis-backed implementation of PointerStorage protocol.

    Provides persistent key-value storage for Gmail message pointers.
    Automatically handles connection errors gracefully.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        decode_responses: bool = True,
    ) -> None:
        """
        Initialize Redis connection.

        Args:
            host: Redis server hostname
            port: Redis server port
            db: Redis database number
            decode_responses: If True, decode responses as UTF-8 strings

        Raises:
            redis.ConnectionError: If connection to Redis fails
        """
        try:
            self.client = redis.Redis(
                host=host,
                port=port,
                db=db,
                decode_responses=decode_responses,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            # Test connection
            self.client.ping()
            logger.info(f"Connected to Redis at {host}:{port}/{db}")
        except redis.ConnectionError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error connecting to Redis: {e}")
            raise

    def get(self, key: str) -> Optional[str]:
        """
        Get value by key from Redis.

        Args:
            key: Storage key

        Returns:
            Value as string, or None if key doesn't exist or error occurs
        """
        try:
            value = self.client.get(key)
            return value if value is not None else None
        except redis.RedisError as e:
            logger.error(f"Redis GET error for key '{key}': {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting key '{key}': {e}")
            return None

    def set(self, key: str, value: str) -> None:
        """
        Set value by key in Redis.

        Args:
            key: Storage key
            value: Value to store

        Raises:
            redis.RedisError: If Redis operation fails
        """
        try:
            self.client.set(key, value)
            logger.debug(f"Set Redis key '{key}' = '{value}'")
        except redis.RedisError as e:
            logger.error(f"Redis SET error for key '{key}': {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error setting key '{key}': {e}")
            raise

    def delete(self, key: str) -> None:
        """
        Delete key from Redis.

        Args:
            key: Storage key to delete
        """
        try:
            self.client.delete(key)
            logger.debug(f"Deleted Redis key '{key}'")
        except redis.RedisError as e:
            logger.warning(f"Redis DELETE error for key '{key}': {e}")
        except Exception as e:
            logger.warning(f"Unexpected error deleting key '{key}': {e}")

    def exists(self, key: str) -> bool:
        """
        Check if key exists in Redis.

        Args:
            key: Storage key

        Returns:
            True if key exists, False otherwise
        """
        try:
            return bool(self.client.exists(key))
        except redis.RedisError as e:
            logger.warning(f"Redis EXISTS error for key '{key}': {e}")
            return False
        except Exception as e:
            logger.warning(f"Unexpected error checking key '{key}': {e}")
            return False

