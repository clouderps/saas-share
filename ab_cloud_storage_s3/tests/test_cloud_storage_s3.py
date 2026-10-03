from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from ..models import ir_attachment as s3mod
from ..models.res_config_settings import merge_cors


class FakeClient:
    def generate_presigned_url(self, op, Params, ExpiresIn):
        return f"https://{Params['Bucket']}.s3.amazonaws.com/{Params['Key']}?op={op}&exp={ExpiresIn}"


@tagged('post_install', '-at_install')
class TestCloudStorageS3(TransactionCase):

    def setUp(self):
        super().setUp()
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('cloud_storage_provider', 's3')
        for key, value in (('bucket', 'tenant-bucket'), ('region', 'eu-west-1'),
                           ('prefix', 'entity_7/filestore'),
                           ('access_key_id', 'AK'), ('secret_access_key', 'SK')):
            ICP.set_param(f'ab_s3.{key}', value)
        patcher = patch.object(s3mod, 's3_client', lambda settings: FakeClient())
        patcher.start()
        self.addCleanup(patcher.stop)

    def _attachment(self, name='big report.pdf'):
        return self.env['ir.attachment'].create({'name': name, 'type': 'url', 'url': 'about:blank'})

    def test_url_goes_under_the_tenant_folder_and_round_trips(self):
        att = self._attachment()
        url = att._generate_cloud_storage_url()
        self.assertTrue(url.startswith('https://tenant-bucket.s3.eu-west-1.amazonaws.com/entity_7/cloud_storage/'))
        att.url = url
        info = att._get_cloud_storage_s3_info()
        self.assertEqual((info['bucket'], info['region']), ('tenant-bucket', 'eu-west-1'))
        self.assertTrue(info['key'].startswith(f'entity_7/cloud_storage/{att.id}/'))
        self.assertTrue(info['key'].endswith('/big report.pdf'))  # unquoted back

    def test_own_parameters_override_the_tenant_storage(self):
        self.env['ir.config_parameter'].sudo().set_param('cloud_storage_s3_bucket_name', 'other')
        self.env['ir.config_parameter'].sudo().set_param('cloud_storage_s3_prefix', 'x/y')
        url = self._attachment()._generate_cloud_storage_url()
        self.assertTrue(url.startswith('https://other.s3.eu-west-1.amazonaws.com/x/y/cloud_storage/'))

    def test_signed_upload_and_download_info(self):
        att = self._attachment()
        att.url = att._generate_cloud_storage_url()
        up = att._generate_cloud_storage_upload_info()
        self.assertEqual((up['method'], up['response_status']), ('PUT', 200))
        self.assertIn('op=put_object', up['url'])
        down = att._generate_cloud_storage_download_info()
        self.assertIn('op=get_object', down['url'])
        self.assertEqual(down['time_to_expiry'], att._cloud_storage_download_url_time_to_expiry)

    def test_configuration_needs_credentials(self):
        Settings = self.env['res.config.settings']
        self.assertTrue(Settings._get_cloud_storage_configuration())
        self.env['ir.config_parameter'].sudo().set_param('ab_s3.secret_access_key', '')
        self.assertEqual(Settings._get_cloud_storage_configuration(), {})

    def test_other_provider_is_not_hijacked(self):
        self.env['ir.config_parameter'].sudo().set_param('cloud_storage_provider', 'google')
        self.assertFalse(self.env['ir.attachment']._cloud_storage_s3_active())

    def test_cors_rules_are_only_ever_added(self):
        existing = [{'ID': 'backups', 'AllowedOrigins': ['https://x.example'], 'AllowedMethods': ['GET']}]
        rules, changed = merge_cors(existing, 'https://fayia.ghaima.sa', 300)
        self.assertTrue(changed)
        self.assertEqual(rules[0], existing[0])  # untouched
        self.assertEqual(rules[1]['AllowedOrigins'], ['https://fayia.ghaima.sa'])
        wildcard = [{'AllowedOrigins': ['https://*.ghaima.sa'], 'AllowedMethods': ['GET', 'PUT']}]
        self.assertEqual(merge_cors(wildcard, 'https://qira.ghaima.sa', 300), (wildcard, False))
