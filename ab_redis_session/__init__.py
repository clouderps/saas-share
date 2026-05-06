import logging
from . import models

_logger = logging.getLogger(__name__)


def _post_init_hook(env):
    """Activate Redis session store if configured."""
    from . models.redis_session import _setup_redis_session_store
    _setup_redis_session_store()
    _logger.info('Redis session store initialized (if configured)')
