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
        # the list() reverse parse (key.split(':')[-1]) must recover the sid
        self.assertEqual(key.split(':')[-1], 's')
