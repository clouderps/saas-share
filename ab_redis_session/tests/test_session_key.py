from odoo.tests.common import TransactionCase, tagged

from odoo.addons.ab_redis_session.models import redis_session as mod


@tagged('post_install', '-at_install', 'ghaima_redis')
class TestSessionKey(TransactionCase):
    """ab_redis_session._session_key — the per-tenant Redis session key.
    Extracted to module level (the RedisSessionStore that uses it lives in a
    closure) so the namespacing contract is unit-testable: every tenant's
    sessions must be isolated by its prefix when many share one Redis."""

    def test_key_namespaced_by_prefix(self):
        self.assertEqual(mod._session_key('entity_5', 'abc123'), 'entity_5:abc123')

    def test_default_prefix(self):
        self.assertEqual(mod._session_key('odoo_session', 'sid'), 'odoo_session:sid')

    def test_tenant_isolation(self):
        self.assertNotEqual(
            mod._session_key('entity_1', 'sid'),
            mod._session_key('entity_2', 'sid'),
        )

    def test_separator_is_colon(self):
        key = mod._session_key('p', 's')
        self.assertEqual(key, 'p:s')
        # the sid is recoverable from the key
        self.assertEqual(key.split(':')[-1], 's')


class FakeRedis:
    def __init__(self):
        self.data, self.ttls = {}, {}

    def set(self, key, value, ex=None):
        self.data[key], self.ttls[key] = value.encode(), ex

    def get(self, key):
        return self.data.get(key)

    def expire(self, key, ttl):
        self.ttls[key] = ttl

    def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)

    def scan_iter(self, match, count=None):
        import fnmatch
        return [k for k in list(self.data) if fnmatch.fnmatchcase(k, match)]


@tagged('post_install', '-at_install', 'ghaima_redis')
class TestRedisSessionStore(TransactionCase):

    def setUp(self):
        super().setUp()
        from odoo import http
        self.http = http
        self.redis = FakeRedis()
        self.store = mod.RedisSessionStore(self.redis, 'entity_9', 3600, session_class=http.Session,
                                           renew_missing=True)

    def test_save_get_rotate_delete(self):
        session = self.store.new()
        session['login'] = 'cashier'
        self.store.save(session)
        self.assertEqual(self.store.get(session.sid)['login'], 'cashier')  # any node reads it
        old_sid = session.sid
        self.store.rotate(session, None)                                     # what login does
        self.assertNotEqual(session.sid, old_sid)
        self.assertTrue(self.store.get(old_sid).is_new)
        self.assertEqual(self.store.get(session.sid)['login'], 'cashier')
        self.store.delete(session)
        self.assertTrue(self.store.get(session.sid).is_new)

    def test_device_revocation_by_identifier(self):
        session = self.store.new()
        self.store.save(session)
        ident = session.sid[:42]
        self.assertEqual(self.store.get_missing_session_identifiers([ident, 'x' * 42]), {'x' * 42})
        self.store.delete_from_identifiers([ident, '*'])                    # '*' must not match all
        self.assertEqual(self.store.get_missing_session_identifiers([ident]), {ident})

    def test_prefix_isolates_tenants(self):
        other = mod.RedisSessionStore(self.redis, 'entity_10', 3600, session_class=self.http.Session)
        session = self.store.new()
        self.store.save(session)
        self.assertTrue(other.get(session.sid).is_new)
