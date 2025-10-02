"""
Broker health check utilities.
Provides health checking functionality for message brokers like Redis.
"""

import time

from backend.config import get_settings
from backend.utils.logger import get_logger

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = get_logger(__name__)


async def broker_health_check() -> bool:
    """
    Perform broker health check with comprehensive observability.
    
    Currently checks Redis connectivity as the primary message broker.
    
    Returns:
        True if broker is healthy
        
    Raises:
        Exception if broker is not accessible
    """
    start_time = time.time()
    
    try:
        if not REDIS_AVAILABLE:
            logger.warning("Redis client not available, treating as unhealthy")
            raise RuntimeError("Redis client library not installed")
        
        settings = get_settings()
        
        # Create Redis connection
        redis_client = redis.from_url(
            settings.data.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=5.0,
            socket_connect_timeout=5.0
        )
        
        try:
            # Simple ping test
            result = await redis_client.ping()
            
            duration_seconds = time.time() - start_time
            
            if result:
                logger.debug(f"Broker health check passed in {duration_seconds:.3f}s")
                return True
            else:
                raise RuntimeError("Broker health check failed: ping returned False")
                
        finally:
            await redis_client.aclose()
            
    except Exception as e:
        duration_seconds = time.time() - start_time
        logger.error(f"Broker health check failed in {duration_seconds:.3f}s: {e}")
        raise
