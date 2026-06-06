from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'ghaima_s3')
class TestS3Key(TransactionCase):
    """ir.attachment._s3_key — builds the S3 object key from the stored
    filename, scoped by the per-tenant prefix (e.g. 'entity_5/filestore').
    The prefix is what partitions every tenant inside the one shared bucket,
    so the join must be exact and prefix-less attachments must pass through
    unchanged. _s3_config is mocked so the test needs no real S3/config."""

    def setUp(self):
        super().setUp()
        self.Att = self.env['ir.attachment']

    def _with_prefix(self, prefix):
        # patch the method on the model class so the recordset call sees it
        return patch.object(type(self.Att), '_s3_config',
                            return_value={'prefix': prefix})

    def test_key_with_tenant_prefix(self):
        with self._with_prefix('entity_5/filestore'):
            self.assertEqual(
                self.Att._s3_key('ab/cdef1234'),
                'entity_5/filestore/ab/cdef1234',
            )

    def test_key_without_prefix_passthrough(self):
        with self._with_prefix(''):
            self.assertEqual(self.Att._s3_key('ab/cdef1234'), 'ab/cdef1234')

    def test_key_with_none_prefix_passthrough(self):
        with self._with_prefix(None):
            self.assertEqual(self.Att._s3_key('ab/cdef1234'), 'ab/cdef1234')

    def test_prefix_isolation_between_tenants(self):
        fname = 'aa/bbccddee'
        with self._with_prefix('entity_1/filestore'):
            k1 = self.Att._s3_key(fname)
        with self._with_prefix('entity_2/filestore'):
            k2 = self.Att._s3_key(fname)
        self.assertNotEqual(k1, k2)
        self.assertTrue(k1.startswith('entity_1/'))
        self.assertTrue(k2.startswith('entity_2/'))
