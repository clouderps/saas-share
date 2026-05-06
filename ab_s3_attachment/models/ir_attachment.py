import hashlib
import logging
import threading

from odoo import api, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Probe boto3 once at import time. If missing we fall back to local-disk
# storage instead of returning HTTP 400 on every asset bundle write — a
# missing optional dep should never blank the whole tenant site.
try:
    import boto3 as _boto3
    HAS_BOTO3 = True
except ImportError:
    _boto3 = None
    HAS_BOTO3 = False
    _logger.warning(
        'boto3 is not installed — S3 attachment storage is disabled and all '
        'attachments (including compiled asset bundles) will use local disk. '
        'Install boto3 to enable S3: pip install boto3'
    )

# Thread-safe S3 client cache
_s3_client_cache = {}
_s3_client_lock = threading.Lock()


def _get_s3_config(env):
    """Read S3 configuration from ir.config_parameter."""
    ICP = env['ir.config_parameter'].sudo()
    return {
        'bucket': ICP.get_param('ab_s3.bucket', ''),
        'prefix': ICP.get_param('ab_s3.prefix', ''),
        'region': ICP.get_param('ab_s3.region', 'us-east-1'),
        'access_key_id': ICP.get_param('ab_s3.access_key_id', ''),
        'secret_access_key': ICP.get_param('ab_s3.secret_access_key', ''),
        'max_storage_bytes': int(ICP.get_param('ab_s3.max_storage_bytes', '0')),
    }


def _get_s3_client(config):
    """Get or create a cached boto3 S3 client."""
    cache_key = f"{config['access_key_id']}_{config['region']}_{config['bucket']}"
    with _s3_client_lock:
        if cache_key in _s3_client_cache:
            return _s3_client_cache[cache_key]

    if not HAS_BOTO3:
        # Caller should have already gated on _is_s3_storage(); raise to keep
        # signature contract for any direct caller.
        raise UserError(_('boto3 is not installed. Run: pip install boto3'))

    client = _boto3.client(
        's3',
        aws_access_key_id=config['access_key_id'],
        aws_secret_access_key=config['secret_access_key'],
        region_name=config['region'],
    )
    with _s3_client_lock:
        _s3_client_cache[cache_key] = client
    return client


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    def _is_s3_storage(self):
        """Check if S3 storage is configured and active.

        Returns False when boto3 isn't installed so all read/write/delete
        paths transparently fall through to the base local-disk
        implementation instead of 400-ing the request. The startup warning
        in HAS_BOTO3 surfaces the misconfig to admins.
        """
        if not HAS_BOTO3:
            return False
        location = self.env['ir.config_parameter'].sudo().get_param(
            'ir_attachment.location', 'file'
        )
        return location == 's3'

    def _s3_config(self):
        """Get S3 configuration, cached on the environment."""
        if not hasattr(self.env, '_s3_config_cache'):
            self.env._s3_config_cache = _get_s3_config(self.env)
        return self.env._s3_config_cache

    def _s3_client(self):
        """Get boto3 S3 client."""
        config = self._s3_config()
        if not config['bucket'] or not config['access_key_id']:
            raise UserError(_('S3 storage is not properly configured.'))
        return _get_s3_client(config)

    def _s3_key(self, fname):
        """Build full S3 key from filename."""
        prefix = self._s3_config()['prefix']
        if prefix:
            return f"{prefix}/{fname}"
        return fname

    # ==================== Core Overrides ====================

    def _file_read(self, fname):
        if not self._is_s3_storage():
            return super()._file_read(fname)

        key = self._s3_key(fname)
        try:
            response = self._s3_client().get_object(
                Bucket=self._s3_config()['bucket'],
                Key=key
            )
            return response['Body'].read()
        except Exception as e:
            _logger.warning('S3 _file_read failed for key %s: %s', key, e)
            # Fallback to local filesystem (for migration period)
            try:
                return super()._file_read(fname)
            except Exception:
                pass
        return b''

    def _to_http_stream(self):
        """Override to serve files from S3 instead of local disk.

        The base Odoo method uses stream.type='path' and os.stat() to serve
        files directly from the filesystem. This crashes with FileNotFoundError
        when files are on S3. We override to use stream.type='data' with
        the file content read from S3.
        """
        if not self._is_s3_storage() or not self.store_fname:
            return super()._to_http_stream()

        from odoo.http import Stream, request
        self.ensure_one()

        stream = Stream(
            mimetype=self.mimetype,
            download_name=self.name,
            etag=self.checksum,
            public=self.public,
        )

        # Read from S3
        data = self._file_read(self.store_fname)
        if data:
            stream.type = 'data'
            stream.data = data
            stream.size = len(data)
        elif self.db_datas:
            stream.type = 'data'
            stream.data = self.raw
        else:
            stream.type = 'data'
            stream.data = b''
            stream.size = 0

        return stream

    def _file_write(self, bin_value, checksum):
        if not self._is_s3_storage():
            return super()._file_write(bin_value, checksum)

        fname = checksum[:2] + '/' + checksum
        key = self._s3_key(fname)
        config = self._s3_config()

        # Check if already exists (dedup by checksum)
        if self._s3_object_exists(key):
            return fname

        # Check quota before write
        self._check_s3_quota(len(bin_value))

        try:
            self._s3_client().put_object(
                Bucket=config['bucket'],
                Key=key,
                Body=bin_value,
            )
        except Exception as e:
            _logger.error('S3 _file_write failed for key %s: %s', key, e)
            raise UserError(_('Failed to upload file to S3: %s') % str(e))

        return fname

    def _file_delete(self, fname):
        if not self._is_s3_storage():
            return super()._file_delete(fname)

        key = self._s3_key(fname)
        try:
            self._s3_client().delete_object(
                Bucket=self._s3_config()['bucket'],
                Key=key
            )
        except Exception as e:
            _logger.warning('S3 _file_delete failed for key %s: %s', key, e)

    # ==================== Helpers ====================

    def _s3_object_exists(self, key):
        """Check if an S3 object exists."""
        try:
            self._s3_client().head_object(
                Bucket=self._s3_config()['bucket'],
                Key=key
            )
            return True
        except Exception:
            return False

    def _check_s3_quota(self, new_bytes):
        """Check if adding new_bytes would exceed the S3 quota."""
        max_bytes = self._s3_config()['max_storage_bytes']
        if max_bytes <= 0:
            return  # unlimited

        # Fast check via DB (no S3 API call)
        self.env.cr.execute(
            "SELECT COALESCE(SUM(file_size), 0) FROM ir_attachment "
            "WHERE store_fname IS NOT NULL"
        )
        current_bytes = self.env.cr.fetchone()[0]

        if current_bytes + new_bytes > max_bytes:
            used_gb = current_bytes / (1024 ** 3)
            max_gb = max_bytes / (1024 ** 3)
            raise UserError(
                _('Storage quota exceeded.\n\n'
                  'Used: %.2f GB / %.2f GB\n'
                  'Cannot upload %.2f MB.\n\n'
                  'Please contact your administrator to increase storage.')
                % (used_gb, max_gb, new_bytes / (1024 ** 2))
            )

    @api.autovacuum
    def _gc_s3_file_store(self):
        """Garbage collect orphaned S3 objects."""
        if not self._is_s3_storage():
            return

        config = self._s3_config()
        client = self._s3_client()
        prefix = config['prefix']
        bucket = config['bucket']

        if not prefix:
            _logger.warning('S3 GC skipped: no prefix configured')
            return

        # Get all store_fname values from DB
        self.env.cr.execute(
            "SELECT store_fname FROM ir_attachment WHERE store_fname IS NOT NULL"
        )
        db_fnames = set(row[0] for row in self.env.cr.fetchall())

        # List all S3 objects under prefix
        paginator = client.get_paginator('list_objects_v2')
        to_delete = []
        for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/"):
            for obj in page.get('Contents', []):
                s3_key = obj['Key']
                # Extract fname from key (remove prefix)
                fname = s3_key[len(prefix) + 1:]  # strip prefix/
                if fname and fname not in db_fnames:
                    to_delete.append({'Key': s3_key})

        # Batch delete orphans (max 1000 per request)
        if to_delete:
            _logger.info('S3 GC: deleting %d orphan objects', len(to_delete))
            for i in range(0, len(to_delete), 1000):
                batch = to_delete[i:i + 1000]
                client.delete_objects(
                    Bucket=bucket,
                    Delete={'Objects': batch}
                )
            _logger.info('S3 GC: cleanup complete')
        else:
            _logger.info('S3 GC: no orphans found')

    @api.model
    def _s3_migrate_local_to_s3(self):
        """Migrate all local attachments to S3. Called from management platform."""
        if not self._is_s3_storage():
            return {'status': 'error', 'message': 'S3 not configured'}

        attachments = self.search([('store_fname', '!=', False)])
        migrated = 0
        errors = 0
        for att in attachments:
            key = self._s3_key(att.store_fname)
            if not self._s3_object_exists(key):
                try:
                    data = super(IrAttachment, att)._file_read(att.store_fname)
                    if data:
                        self._s3_client().put_object(
                            Bucket=self._s3_config()['bucket'],
                            Key=key,
                            Body=data,
                        )
                        migrated += 1
                except Exception as e:
                    _logger.warning('S3 migration failed for %s: %s', att.store_fname, e)
                    errors += 1
            else:
                migrated += 1  # already on S3
        return {'status': 'ok', 'migrated': migrated, 'errors': errors, 'total': len(attachments)}

    def _s3_get_usage_bytes(self):
        """Get total S3 usage in bytes for this entity's prefix."""
        config = self._s3_config()
        if not config['bucket'] or not config['prefix']:
            return 0

        client = self._s3_client()
        total = 0
        paginator = client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=config['bucket'], Prefix=f"{config['prefix']}/"):
            for obj in page.get('Contents', []):
                total += obj.get('Size', 0)
        return total
