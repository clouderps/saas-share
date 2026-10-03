import fnmatch
from datetime import datetime, timezone

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError, ValidationError

from .ir_attachment import s3_client, s3_settings

CORS_RULE_ID = 'odoo-cloud-storage'


def merge_cors(rules, origin, max_age):
    """Bucket CORS rules plus one allowing ``origin`` to GET/PUT, unless an
    existing rule already covers it. The bucket is shared with backups and
    every tenant's filestore: rules are only ever added, never replaced.
    Returns (rules, changed)."""
    for rule in rules:
        methods = set(rule.get('AllowedMethods') or [])
        if {'GET', 'PUT'} <= methods and any(
                fnmatch.fnmatchcase(origin, pattern) for pattern in rule.get('AllowedOrigins') or []):
            return rules, False
    return rules + [{
        'ID': f'{CORS_RULE_ID}-{origin.split("//")[-1]}'[:255],
        'AllowedOrigins': [origin],
        'AllowedMethods': ['GET', 'PUT'],
        'AllowedHeaders': ['*'],
        'ExposeHeaders': ['ETag'],
        'MaxAgeSeconds': int(max_age),
    }], True


class CloudStorageSettings(models.TransientModel):
    """Leave the S3 fields empty to use the tenant's ab_s3_attachment settings."""
    _inherit = 'res.config.settings'

    cloud_storage_provider = fields.Selection(selection_add=[('s3', 'Amazon S3')])

    cloud_storage_s3_bucket_name = fields.Char(
        string='S3 Bucket', config_parameter='cloud_storage_s3_bucket_name')
    cloud_storage_s3_region = fields.Char(
        string='S3 Region', config_parameter='cloud_storage_s3_region')
    cloud_storage_s3_prefix = fields.Char(
        string='S3 Folder', config_parameter='cloud_storage_s3_prefix',
        help='Objects go under <folder>/cloud_storage/. Empty: the instance folder used for its files.')
    cloud_storage_s3_access_key_id = fields.Char(
        string='S3 Access Key ID', config_parameter='cloud_storage_s3_access_key_id')
    cloud_storage_s3_secret_access_key = fields.Char(
        string='S3 Secret Access Key', config_parameter='cloud_storage_s3_secret_access_key')

    def _setup_cloud_storage_provider(self):
        ICP = self.env['ir.config_parameter']
        if ICP.get_param('cloud_storage_provider') != 's3':
            return super()._setup_cloud_storage_provider()
        settings = s3_settings(self.env)
        if not all((settings['bucket'], settings['access_key_id'], settings['secret_access_key'])):
            raise ValidationError(_('Amazon S3 is not configured: bucket and access keys are required.'))
        Attachment = self.env['ir.attachment']
        key = '/'.join(p for p in (settings['prefix'], 'cloud_storage', '0',
                                   f'{datetime.now(timezone.utc):%Y%m%dT%H%M%S%f}.txt') if p)
        put = requests.put(Attachment._generate_cloud_storage_s3_signed_url(
            settings['bucket'], key, 'PUT', Attachment._cloud_storage_upload_url_time_to_expiry),
            data=b'', timeout=10)
        if put.status_code != 200:
            raise ValidationError(_('These credentials cannot upload to the bucket.\n%s', put.text[:500]))
        get = requests.get(Attachment._generate_cloud_storage_s3_signed_url(
            settings['bucket'], key, 'GET', Attachment._cloud_storage_download_url_time_to_expiry), timeout=10)
        if get.status_code != 200:
            raise ValidationError(_('These credentials cannot download from the bucket.\n%s', get.text[:500]))
        client = s3_client(settings)
        client.delete_object(Bucket=settings['bucket'], Key=key)

        # browsers PUT/GET straight to S3: the bucket must allow this origin
        origin = (ICP.get_param('web.base.url') or '').rstrip('/')
        try:
            rules = client.get_bucket_cors(Bucket=settings['bucket']).get('CORSRules', [])
        except client.exceptions.ClientError as exc:
            if exc.response.get('Error', {}).get('Code') != 'NoSuchCORSConfiguration':
                raise ValidationError(_("Cannot read the bucket's CORS rules.\n%s", exc)) from exc
            rules = []
        rules, changed = merge_cors(rules, origin, Attachment._cloud_storage_download_url_time_to_expiry)
        if changed:
            try:
                client.put_bucket_cors(Bucket=settings['bucket'], CORSConfiguration={'CORSRules': rules})
            except client.exceptions.ClientError as exc:
                raise ValidationError(_(
                    'The bucket does not allow browser uploads from %(origin)s and these credentials '
                    'cannot add the CORS rule.\n%(err)s', origin=origin, err=exc)) from exc

    def _get_cloud_storage_configuration(self):
        if self.env['ir.config_parameter'].sudo().get_param('cloud_storage_provider') != 's3':
            return super()._get_cloud_storage_configuration()
        settings = s3_settings(self.env)
        configuration = {k: settings[k] for k in ('bucket', 'region', 'access_key_id', 'secret_access_key')}
        return configuration if all(configuration.values()) else {}

    def _check_cloud_storage_uninstallable(self):
        if self.env['ir.config_parameter'].get_param('cloud_storage_provider') != 's3':
            return super()._check_cloud_storage_uninstallable()
        self.env.cr.execute("""
            SELECT 1 FROM ir_attachment
             WHERE type = 'cloud_storage' AND url LIKE 'https://%%.amazonaws.com/%%' LIMIT 1""")
        if self.env.cr.fetchone():
            raise UserError(_('Some Amazon S3 attachments are in use, please migrate cloud storages '
                              'before disabling the provider.'))
