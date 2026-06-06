"""
Redis Session Store for Odoo 18 — Multi-Node HA Support

Replaces werkzeug's filesystem session store with Redis.
Sessions are shared across all Odoo workers/nodes.

What's stored in the session:
- Login state (uid, db, login)
- CSRF tokens
- Shopping cart data
- Wizard state
- Form draft values

What this solves:
- User stays logged in when routed to any app node
- No session loss on container restart
- Concurrent workers share sessions
- Automatic session expiry via Redis TTL
"""

import json
import logging
import pickle
import threading

from odoo import api, models
from odoo.tools import config as odoo_config

_logger = logging.getLogger(__name__)

# Redis client singleton
_redis_client = None
_redis_lock = threading.Lock()
_redis_prefix = 'odoo_session'
_redis_ttl = 86400  # 24 hours


def _session_key(prefix, sid):
    """Build the Redis key for a session id, namespaced by the per-tenant
    ``prefix`` (e.g. 'entity_5') so tenants/nodes sharing one Redis never
    collide. Module-level + pure so it is unit-testable — the
    RedisSessionStore that uses it lives inside the _setup_redis_session_store
    closure and can't be imported directly."""
    return f'{prefix}:{sid}'


def _get_redis_client():
    """Get or create Redis client singleton."""
    global _redis_client
    if _redis_client is not None:
        try:
            _redis_client.ping()
            return _redis_client
        except Exception:
            _redis_client = None

    redis_url = odoo_config.get('redis_url', '')
    if not redis_url:
        return None

    with _redis_lock:
        if _redis_client is not None:
            return _redis_client
        try:
            import redis
            _redis_client = redis.Redis.from_url(redis_url, decode_responses=False)
            _redis_client.ping()
            _logger.info('Redis session store connected: %s', redis_url.split('@')[-1])
            return _redis_client
        except Exception as e:
            _logger.warning('Redis connection failed: %s — falling back to filesystem', e)
            return None


def _setup_redis_session_store():
    """Replace Odoo's session store with Redis-backed store."""
    redis_url = odoo_config.get('redis_url', '')
    if not redis_url:
        _logger.info('Redis URL not configured (redis_url in odoo.conf). Using filesystem sessions.')
        return

    global _redis_prefix, _redis_ttl
    _redis_prefix = odoo_config.get('redis_session_prefix', 'odoo_session')
    _redis_ttl = int(odoo_config.get('redis_session_ttl', '86400'))

    client = _get_redis_client()
    if not client:
        return

    try:
        import odoo.http
        from werkzeug.contrib.sessions import SessionStore
    except ImportError:
        try:
            from werkzeug.middleware.session import SessionStore
        except ImportError:
            _logger.warning('Cannot import SessionStore — Redis sessions not activated')
            return

    class RedisSessionStore(SessionStore):
        """Werkzeug-compatible session store backed by Redis."""

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.redis = client
            self.prefix = _redis_prefix
            self.ttl = _redis_ttl

        def _key(self, sid):
            return _session_key(self.prefix, sid)

        def save(self, session):
            key = self._key(session.sid)
            try:
                data = pickle.dumps(dict(session))
                self.redis.setex(key, self.ttl, data)
            except Exception as e:
                _logger.warning('Redis session save failed for %s: %s', session.sid, e)

        def delete(self, session):
            key = self._key(session.sid)
            try:
                self.redis.delete(key)
            except Exception as e:
                _logger.warning('Redis session delete failed for %s: %s', session.sid, e)

        def get(self, sid):
            if not self.is_valid_key(sid):
                return self.new()
            key = self._key(sid)
            try:
                data = self.redis.get(key)
                if data:
                    session_data = pickle.loads(data)
                    return self.session_class(session_data, sid, False)
            except Exception as e:
                _logger.warning('Redis session get failed for %s: %s', sid, e)
            return self.session_class({}, sid, True)

        def list(self):
            try:
                keys = self.redis.keys(f'{self.prefix}:*')
                return [k.decode().split(':')[-1] for k in keys]
            except Exception:
                return []

    # Monkey-patch Odoo's session store
    try:
        # Odoo 18 uses odoo.http.root.session_store
        if hasattr(odoo.http, 'root') and odoo.http.root:
            odoo.http.root.session_store = RedisSessionStore(
                session_class=odoo.http.Session
            )
            _logger.info(
                'Redis session store activated (prefix=%s, ttl=%ss)',
                _redis_prefix, _redis_ttl
            )
        else:
            # Root not initialized yet — hook into server startup
            _logger.info('Redis session store will be activated on server start')
            original_serve = getattr(odoo.http, 'serve', None)
            if original_serve:
                def patched_serve(*args, **kwargs):
                    result = original_serve(*args, **kwargs)
                    if hasattr(odoo.http, 'root') and odoo.http.root:
                        odoo.http.root.session_store = RedisSessionStore(
                            session_class=odoo.http.Session
                        )
                        _logger.info('Redis session store activated (deferred)')
                    return result
                odoo.http.serve = patched_serve
    except Exception as e:
        _logger.error('Failed to activate Redis session store: %s', e)


class RedisSessionConfig(models.TransientModel):
    _name = 'redis.session.config'
    _description = 'Redis Session Configuration (transient)'

    @api.model
    def get_redis_info(self):
        """Return Redis connection info for diagnostics."""
        client = _get_redis_client()
        if not client:
            return {'status': 'disconnected', 'reason': 'No Redis URL configured or connection failed'}
        try:
            info = client.info('server')
            keys = client.keys(f'{_redis_prefix}:*')
            return {
                'status': 'connected',
                'redis_version': info.get('redis_version'),
                'prefix': _redis_prefix,
                'ttl': _redis_ttl,
                'active_sessions': len(keys),
            }
        except Exception as e:
            return {'status': 'error', 'reason': str(e)}
