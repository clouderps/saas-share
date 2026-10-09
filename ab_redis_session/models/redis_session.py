"""
Redis session store for Odoo 18 — sessions shared by every app node.

Odoo keeps sessions as files on the node that served the login, so behind a
load balancer a user routed to another node is logged out. This store keeps
them in Redis instead, built on Odoo's own FilesystemSessionStore so login
rotation, the session token and device revocation keep their exact behaviour;
only where the bytes live changes.

Enable it in the server config (it must load before the first request, so
also list the module in server_wide_modules):

    server_wide_modules = base,web,ab_redis_session
    redis_url = redis://:<password>@<host>:6379/0
    redis_session_prefix = entity_69        # one prefix per tenant
    redis_session_ttl = 604800              # optional, default = Odoo's 7 days

Without redis_url nothing changes. If Redis is unreachable at start-up the
node keeps file sessions and logs a warning.

Real-time notifications (bus) need nothing here: Odoo 18's bus goes through
PostgreSQL NOTIFY, which every node sharing the database already receives.
"""
import json
import logging

from odoo import api, http, models
from odoo.tools import config as odoo_config

_logger = logging.getLogger(__name__)

_redis_client = None


def _session_key(prefix, sid):
    """Redis key of a session, namespaced per tenant so tenants sharing one
    Redis never see each other's sessions."""
    return f'{prefix}:{sid}'


def _get_redis_client():
    global _redis_client
    if _redis_client is None and odoo_config.get('redis_url'):
        import redis
        _redis_client = redis.Redis.from_url(odoo_config['redis_url'], socket_timeout=2,
                                             socket_connect_timeout=2, health_check_interval=30)
    return _redis_client


class RedisSessionStore(http.FilesystemSessionStore):
    """Odoo's store with Redis as the storage. rotate(), generate_key() and
    is_valid_key() are inherited unchanged."""

    def __init__(self, client, prefix, ttl, **kwargs):
        super().__init__(odoo_config.session_dir, **kwargs)
        self.redis, self.prefix, self.ttl = client, prefix, ttl

    def _key(self, sid):
        return _session_key(self.prefix, sid)

    def save(self, session):
        self.redis.set(self._key(session.sid), json.dumps(dict(session)), ex=self.ttl)

    def get(self, sid):
        if not self.is_valid_key(sid):
            return self.new()
        key = self._key(sid)
        data = self.redis.get(key)
        if data is None:
            return self.session_class({}, sid, True)
        self.redis.expire(key, self.ttl)  # sliding expiry, like the file mtime
        try:
            return self.session_class(json.loads(data), sid, False)
        except ValueError:
            return self.session_class({}, sid, True)

    def delete(self, session):
        self.redis.delete(self._key(session.sid))

    def vacuum(self, max_lifetime=None):
        """Redis expires sessions itself (TTL)."""

    def _keys_for(self, identifier):
        # an identifier is the first 42 characters of a sid
        return list(self.redis.scan_iter(match=self._key(identifier) + '*', count=100))

    def get_missing_session_identifiers(self, identifiers):
        return {i for i in set(identifiers) if not self._keys_for(i)}

    def delete_from_identifiers(self, identifiers):
        for identifier in identifiers:
            if http._session_identifier_re.match(identifier):  # never a broader pattern
                keys = self._keys_for(identifier)
                if keys:
                    self.redis.delete(*keys)


def install_session_store():
    """Swap the session store of this process. Called when the module is
    imported (server_wide_modules makes that happen at start-up)."""
    if not odoo_config.get('redis_url'):
        return False
    try:
        client = _get_redis_client()
        client.ping()
    except Exception as e:  # noqa: BLE001 — keep serving with file sessions
        _logger.warning('Redis sessions NOT active (%s); using file sessions on this node', e)
        return False
    ttl = int(odoo_config.get('redis_session_ttl') or http.SESSION_LIFETIME)
    prefix = odoo_config.get('redis_session_prefix') or 'odoo_session'
    # Application.session_store is a lazy property: setting the instance
    # attribute replaces it for every request of this process.
    http.root.session_store = RedisSessionStore(client, prefix, ttl, session_class=http.Session,
                                                renew_missing=True)
    _logger.info('Redis sessions active (prefix=%s, ttl=%ss)', prefix, ttl)
    return True


class RedisSessionConfig(models.TransientModel):
    _name = 'redis.session.config'
    _description = 'Redis Session Configuration (transient)'

    @api.model
    def get_redis_info(self):
        """Diagnostics for the cockpit."""
        store = http.root.session_store
        if not isinstance(store, RedisSessionStore):
            return {'status': 'disconnected', 'reason': 'This node uses file sessions'}
        try:
            info = store.redis.info('server')
            count = sum(1 for _ in store.redis.scan_iter(match=f'{store.prefix}:*', count=500))
            return {'status': 'connected', 'redis_version': info.get('redis_version'),
                    'prefix': store.prefix, 'ttl': store.ttl, 'active_sessions': count}
        except Exception as e:  # noqa: BLE001
            return {'status': 'error', 'reason': str(e)}
