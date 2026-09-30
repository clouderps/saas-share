"""Signed links for every file size, self-healing, and a safe GC."""
import base64
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from odoo.tests.common import HttpCase, tagged

from odoo.addons.ab_s3_attachment.models import ir_attachment as mod
from .fake_s3 import FakeS3

PREFIX = 'entity_99/filestore'


@tagged('post_install', '-at_install', 'ghaima_s3')
class TestS3Serving(HttpCase):

    def setUp(self):
        super().setUp()
        self.s3 = FakeS3()
        patcher = patch.object(mod, '_get_s3_client', return_value=self.s3)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.ICP = self.env['ir.config_parameter'].sudo()
        for k, v in {'ab_s3.bucket': 'test-bucket', 'ab_s3.prefix': PREFIX,
                     'ab_s3.region': 'me-south-1', 'ab_s3.access_key_id': 'AKIATEST',
                     'ab_s3.secret_access_key': 'x', 'ab_s3.signed_urls': 'True',
                     'ab_s3.signed_url_ttl': '300'}.items():
            self.ICP.set_param(k, v)

    def _s3_on(self):
        self.ICP.set_param('ir_attachment.location', 's3')
        self.env.invalidate_all()
        if hasattr(self.env, '_s3_config_cache'):
            del self.env._s3_config_cache

    def _att(self, data, name='doc.pdf', mimetype='application/pdf'):
        return self.env['ir.attachment'].create({
            'name': name, 'raw': data, 'mimetype': mimetype, 'public': True})

    def _get(self, url):
        return self.url_open(url, allow_redirects=False)

    def test_every_size_redirects_to_a_signed_link(self):
        self._s3_on()
        for size in (0, 1, 5000, 3_000_000):
            att = self._att(b'x' * size, name=f'f{size}.pdf')
            if not att.store_fname:           # 0-byte attachments store nothing
                continue
            self.assertIn(f"{PREFIX}/{att.store_fname}", self.s3.objects)
            res = self._get(f'/web/content/{att.id}')
            self.assertEqual(res.status_code, 302, size)
            loc = res.headers['Location']
            self.assertIn('test-bucket.s3.test', loc)
            self.assertIn('X-Amz-Expires=300', loc)
            self.assertIn('max-age=290', res.headers.get('Cache-Control', ''))

    def test_download_param_asks_for_attachment_disposition(self):
        self._s3_on()
        att = self._att(b'report', name='تقرير.pdf')
        loc = self._get(f'/web/content/{att.id}?download=true').headers['Location']
        self.assertIn('attachment', loc)
        self.assertIn('filename', loc)

    def test_missing_on_s3_is_served_locally_and_healed(self):
        att = self._att(b'local-only-bytes', name='old.txt', mimetype='text/plain')
        key = f"{PREFIX}/{att.store_fname}"
        self._s3_on()
        self.assertNotIn(key, self.s3.objects)
        res = self._get(f'/web/content/{att.id}')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.content, b'local-only-bytes')
        self.assertIn(key, self.s3.objects)            # healed on the way
        self.assertEqual(self._get(f'/web/content/{att.id}').status_code, 302)

    def test_wkhtmltopdf_and_resized_images_stay_proxied(self):
        self._s3_on()
        png = base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
        att = self._att(png, name='p.png', mimetype='image/png')
        res = self.url_open(f'/web/content/{att.id}', allow_redirects=False,
                            headers={'User-Agent': 'Mozilla/5.0 wkhtmltopdf'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self._get(f'/web/image/{att.id}/64x64').status_code, 200)
        self.assertEqual(self._get(f'/web/image/{att.id}?width=32').status_code, 200)
        self.assertEqual(self._get(f'/web/image/{att.id}').status_code, 302)

    def test_disabled_setting_proxies(self):
        self._s3_on()
        self.ICP.set_param('ab_s3.signed_urls', 'False')
        att = self._att(b'abc', name='a.txt', mimetype='text/plain')
        self.assertEqual(self._get(f'/web/content/{att.id}').status_code, 200)

    def test_private_file_still_needs_access(self):
        self._s3_on()
        att = self.env['ir.attachment'].create({
            'name': 'secret.txt', 'raw': b'secret', 'public': False,
            'res_model': 'res.partner', 'res_id': self.env.user.partner_id.id})
        res = self._get(f'/web/content/{att.id}')         # not logged in
        self.assertNotEqual(res.status_code, 302)


@tagged('post_install', '-at_install', 'ghaima_s3')
class TestS3SelfCheckAndGc(HttpCase):

    def setUp(self):
        super().setUp()
        self.s3 = FakeS3()
        patcher = patch.object(mod, '_get_s3_client', return_value=self.s3)
        patcher.start()
        self.addCleanup(patcher.stop)
        ICP = self.env['ir.config_parameter'].sudo()
        for k, v in {'ab_s3.bucket': 'b', 'ab_s3.prefix': PREFIX,
                     'ab_s3.access_key_id': 'AKIATEST', 'ab_s3.secret_access_key': 'x'}.items():
            ICP.set_param(k, v)
        self.ICP = ICP

    def test_self_check_uploads_everything_missing(self):
        atts = [self.env['ir.attachment'].create({'name': f'n{i}', 'raw': f'data{i}'.encode()})
                for i in range(3)]
        self.ICP.set_param('ir_attachment.location', 's3')
        res = self.env['ir.attachment']._s3_self_check()
        self.assertEqual(res['status'], 'ok')
        self.assertGreaterEqual(res['healed'], 3)
        for a in atts:
            self.assertIn(f"{PREFIX}/{a.store_fname}", self.s3.objects)
        again = self.env['ir.attachment']._s3_self_check()
        self.assertEqual(again['missing'], 0)

    def test_gc_never_deletes_young_or_referenced_objects(self):
        self.ICP.set_param('ir_attachment.location', 's3')
        att = self.env['ir.attachment'].create({'name': 'kept', 'raw': b'kept'})
        old = datetime.now(timezone.utc) - timedelta(days=3)
        self.s3.objects[f'{PREFIX}/zz/orphan_old'] = [b'o', old]
        self.s3.objects[f'{PREFIX}/zz/orphan_new'] = [b'n', datetime.now(timezone.utc)]
        self.s3.objects[f'{PREFIX}/{att.store_fname}'][1] = old
        self.env['ir.attachment']._gc_s3_file_store()
        self.assertNotIn(f'{PREFIX}/zz/orphan_old', self.s3.objects)
        self.assertIn(f'{PREFIX}/zz/orphan_new', self.s3.objects)   # upload in flight
        self.assertIn(f'{PREFIX}/{att.store_fname}', self.s3.objects)

    def test_remote_entry_points_are_admin_only(self):
        from odoo.exceptions import AccessError
        from odoo.tests.common import new_test_user
        self.ICP.set_param('ir_attachment.location', 's3')
        user = new_test_user(self.env, login='s3_plain', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.env['ir.attachment'].with_user(user).s3_self_check()
        self.assertEqual(self.env['ir.attachment'].s3_self_check()['status'], 'ok')
