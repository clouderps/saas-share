import logging
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
from odoo.tools import SQL

_logger = logging.getLogger(__name__)

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
    def _compute_raw(self):
        """Server code that reads the bytes (outgoing mail attachments, merges,
        exports) got b'' for S3 cloud links, so mails went out without the file.
        Read them from S3 like any stored file."""
        super()._compute_raw()
        cloud = self.filtered(lambda a: a.type == 'cloud_storage' and not a.raw and a.url
                              and URL_RE.fullmatch(a.url))
        if not cloud or not self._cloud_storage_s3_active():
            return
        client = s3_client(s3_settings(self.env))
        for att in cloud:
            info = att._get_cloud_storage_s3_info()
            try:
                att.raw = client.get_object(Bucket=info['bucket'], Key=info['key'])['Body'].read()
            except Exception as e:  # noqa: BLE001 — a missing object must not break the caller
                _logger.warning('cloud storage: cannot read attachment %s from S3: %s', att.id, e)

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

    # MIGRATION — Odoo's cloud_storage_migration, S3-native: that module reads
    # the bytes from the local filestore, but tenant files already live on S3
    # (ab_s3_attachment), so each one is a server-side copy, no download.
    def _s3_cloud_migration_candidates(self, limit=None, older_than=None):
        """Odoo's own rules: record/chatter files only. Field binaries
        (images), models whose code reads the bytes (mail.thread.main.attachment
        = invoices/ZATCA, documents) and website/asset files stay S3-backed
        binaries."""
        excluded = (*self._get_cloud_storage_unsupported_models(), 'ir.ui.view', 'website')
        self.env.cr.execute(SQL(
            """SELECT id FROM ir_attachment
                WHERE type = 'binary' AND url IS NULL AND store_fname IS NOT NULL
                  AND res_field IS NULL AND res_model IS NOT NULL AND res_id > 0
                  AND res_model NOT IN %s %s
                ORDER BY id %s""",
            excluded,
            SQL('AND create_date < %s', older_than) if older_than else SQL(),
            SQL('LIMIT %s', limit) if limit else SQL()))
        return self.browse(r[0] for r in self.env.cr.fetchall())

    def _s3_migrate_to_cloud_storage(self):
        """Copy each file to its cloud_storage key, then switch the row to
        type=cloud_storage. Size/checksum/mimetype are kept; the old filestore
        object goes to the GC checklist (deleted only once unreferenced). A
        failed copy leaves the attachment untouched."""
        if not self._cloud_storage_s3_active():
            raise UserError(_('Amazon S3 cloud storage is not enabled.'))
        ICP = self.env['ir.config_parameter'].sudo()
        settings = s3_settings(self.env)
        client = s3_client(settings)
        on_s3 = ICP.get_param('ir_attachment.location') == 's3'
        src_bucket = ICP.get_param('ab_s3.bucket') or settings['bucket']
        src_prefix = (ICP.get_param('ab_s3.prefix') or '').strip('/')
        done = failed = 0
        for att in self:
            url = att._generate_cloud_storage_url()
            key = unquote(URL_RE.fullmatch(url)['key'])
            extra = {'ContentType': att.mimetype or 'application/octet-stream',
                     'ServerSideEncryption': 'AES256'}
            try:
                if on_s3:
                    src = f'{src_prefix}/{att.store_fname}' if src_prefix else att.store_fname
                    client.copy_object(Bucket=settings['bucket'], Key=key, MetadataDirective='REPLACE',
                                       CopySource={'Bucket': src_bucket, 'Key': src}, **extra)
                else:
                    client.put_object(Bucket=settings['bucket'], Key=key, Body=att.raw, **extra)
            except Exception as e:  # noqa: BLE001 — keep going, report the count
                _logger.warning('cloud storage migration: attachment %s not copied: %s', att.id, e)
                failed += 1
                continue
            fname = att.store_fname
            self.env.cr.execute(
                "UPDATE ir_attachment SET type = 'cloud_storage', url = %s, store_fname = NULL, "
                "db_datas = NULL WHERE id = %s", (url, att.id))
            att.invalidate_recordset(['type', 'url', 'store_fname', 'db_datas', 'raw', 'datas'])
            self._file_delete(fname)
            done += 1
        return {'migrated': done, 'failed': failed}

    def _cron_s3_convert_to_cloud_storage(self):
        """Hourly: files the SERVER created (incoming e-mail attachments,
        generated documents...) are always plain binaries - Odoo's direct
        cloud upload only covers browser uploads. Convert the safe set (same
        rules as above) once they are old enough that the code which just
        created them is done reading their bytes."""
        if not self._cloud_storage_s3_active():
            return
        from datetime import timedelta
        from odoo import fields
        hours = int(self.env['ir.config_parameter'].sudo().get_param(
            'cloud_storage_s3_convert_after_hours', '24') or 24)
        cands = self.sudo()._s3_cloud_migration_candidates(
            limit=500, older_than=fields.Datetime.now() - timedelta(hours=hours))
        if cands:
            res = cands._s3_migrate_to_cloud_storage()
            _logger.info('cloud storage: converted %s', res)
