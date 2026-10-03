import re
import threading
from urllib.parse import quote, unquote

try:
    import boto3
    from botocore.config import Config
except ImportError:  # pragma: no cover - boto3 ships in the tenant image
    boto3 = Config = None

from odoo import _, models
from odoo.exceptions import UserError, ValidationError

_clients = {}  # (access key, region) -> boto3 client; signing is local, clients are thread-safe
_clients_lock = threading.Lock()

URL_RE = re.compile(
    r'https://(?P<bucket>[a-z0-9][a-z0-9.\-]*)\.s3\.(?P<region>[a-z0-9\-]+)\.amazonaws\.com/(?P<key>[^?]+)')


def s3_settings(env):
    """Effective S3 settings: the module's own parameters, else the tenant's
    existing ab_s3_attachment ones. The object prefix is the tenant's
    ``entity_<id>`` (ab_s3.prefix minus its ``/filestore`` part)."""
    ICP = env['ir.config_parameter'].sudo()

    def get(own, fallback, default=''):
        return ICP.get_param(f'cloud_storage_s3_{own}') or ICP.get_param(f'ab_s3.{fallback}') or default

    prefix = ICP.get_param('cloud_storage_s3_prefix')
    if not prefix:
        prefix = (ICP.get_param('ab_s3.prefix') or '').strip('/').removesuffix('/filestore')
    return {
        'bucket': get('bucket_name', 'bucket'),
        'region': get('region', 'region', 'us-east-1'),
        'access_key_id': get('access_key_id', 'access_key_id'),
        'secret_access_key': get('secret_access_key', 'secret_access_key'),
        'prefix': prefix.strip('/'),
    }


def s3_client(settings):
    if boto3 is None:
        raise UserError(_('boto3 is not installed.'))
    key = (settings['access_key_id'], settings['region'])
    with _clients_lock:
        client = _clients.get(key)
        if client is None:
            client = _clients[key] = boto3.client(
                's3', region_name=settings['region'],
                aws_access_key_id=settings['access_key_id'],
                aws_secret_access_key=settings['secret_access_key'],
                # virtual-hosted URLs + SigV4: what browsers can PUT/GET to
                config=Config(signature_version='s3v4', s3={'addressing_style': 'virtual'}))
    return client


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    def _cloud_storage_s3_active(self):
        return self.env['ir.config_parameter'].sudo().get_param('cloud_storage_provider') == 's3'

    def _get_cloud_storage_s3_info(self):
        match = URL_RE.fullmatch(self.url or '')
        if not match:
            raise ValidationError(_('%s is not a valid Amazon S3 URL.', self.url))
        return {'bucket': match['bucket'], 'region': match['region'], 'key': unquote(match['key'])}

    def _generate_cloud_storage_s3_signed_url(self, bucket, key, method, expiration):
        settings = s3_settings(self.env)
        return s3_client(settings).generate_presigned_url(
            'put_object' if method == 'PUT' else 'get_object',
            Params={'Bucket': bucket, 'Key': key}, ExpiresIn=int(expiration))

    # OVERRIDES
    def _generate_cloud_storage_url(self):
        if not self._cloud_storage_s3_active():
            return super()._generate_cloud_storage_url()
        settings = s3_settings(self.env)
        key = '/'.join(p for p in (settings['prefix'], 'cloud_storage',
                                   self._generate_cloud_storage_blob_name()) if p)
        return f"https://{settings['bucket']}.s3.{settings['region']}.amazonaws.com/{quote(key)}"

    def _generate_cloud_storage_download_info(self):
        if not self._cloud_storage_s3_active():
            return super()._generate_cloud_storage_download_info()
        info = self._get_cloud_storage_s3_info()
        return {
            'url': self._generate_cloud_storage_s3_signed_url(
                info['bucket'], info['key'], 'GET', self._cloud_storage_download_url_time_to_expiry),
            'time_to_expiry': self._cloud_storage_download_url_time_to_expiry,
        }

    def _generate_cloud_storage_upload_info(self):
        if not self._cloud_storage_s3_active():
            return super()._generate_cloud_storage_upload_info()
        info = self._get_cloud_storage_s3_info()
        return {
            'url': self._generate_cloud_storage_s3_signed_url(
                info['bucket'], info['key'], 'PUT', self._cloud_storage_upload_url_time_to_expiry),
            'method': 'PUT',
            'response_status': 200,
        }
