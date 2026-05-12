import logging
import threading
import time

from odoo import api, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Probe boto3 once at import time. If missing we fall back to local-disk
# storage instead of returning HTTP 400 on every asset bundle write — a
# missing optional dep should never blank the whole tenant site.
try:
    import boto3 as _boto3
    from botocore.exceptions import ClientError as _BotoClientError
    HAS_BOTO3 = True
except ImportError:
    _boto3 = None
    _BotoClientError = Exception
    HAS_BOTO3 = False
    _logger.warning(
        'boto3 is not installed — S3 attachment storage is disabled and all '
        'attachments (including compiled asset bundles) will use local disk. '
        'Install boto3 to enable S3: pip install boto3'
    )

# Thread-safe S3 client cache
_s3_client_cache = {}
_s3_client_lock = threading.Lock()

# Codes worth retrying once. 5xx + SlowDown are transient.
_RETRYABLE_S3_CODES = frozenset({
    'InternalError', 'SlowDown', 'ServiceUnavailable',
    'RequestTimeout', 'RequestTimeoutException',
})


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
        """Read file content from S3, fall back to local disk on miss.

        Three explicit outcomes (logged distinctly so missing files are
        observable without ambiguity):
          - S3 hit            → DEBUG, return data
          - S3 miss, disk hit → INFO  ("served from local disk"), return data
          - both miss         → WARNING (one line w/ key), return b''

        Returning b'' is the same contract as base Odoo's _file_read.
        """
        if not self._is_s3_storage():
            return super()._file_read(fname)

        key = self._s3_key(fname)
        # Attempt S3 first.
        try:
            response = self._s3_client().get_object(
                Bucket=self._s3_config()['bucket'],
                Key=key,
            )
            data = response['Body'].read()
            _logger.debug('ab_s3_attachment: read key=%s size=%d', key, len(data))
            return data
        except Exception as s3_err:
            s3_err_name = type(s3_err).__name__
            # Fall back to local disk. Base _file_read swallows IOError
            # internally and returns b'' — so we must explicitly distinguish
            # "disk had it" from "disk also empty".
            disk_data = b''
            try:
                disk_data = super()._file_read(fname)
            except Exception:
                # Defensive — base swallows IOError but might raise on
                # other oddities. Treat as no-data.
                disk_data = b''

            if disk_data:
                _logger.info(
                    'ab_s3_attachment: S3 miss (%s) — served from local disk: key=%s',
                    s3_err_name, key,
                )
                return disk_data

            _logger.warning(
                'ab_s3_attachment: file missing in S3 AND local disk: key=%s err=%s',
                key, s3_err_name,
            )
            return b''

    def _to_http_stream(self):
        """Override to serve files from S3 instead of local disk.

        Base Odoo uses stream.type='path' + os.stat() which FileNotFoundError-s
        on S3-only attachments. We force type='data' with bytes from S3
        (or local fallback). On true miss we return an HTTP 404 stream
        rather than a 200 with an empty body — empty 200 confuses browser
        cache and the user sees broken images with no clear error.
        """
        if not self._is_s3_storage() or not self.store_fname:
            return super()._to_http_stream()

        from odoo.http import Stream
        from werkzeug.exceptions import NotFound
        self.ensure_one()

        data = self._file_read(self.store_fname)
        if not data and self.db_datas:
            data = self.raw

        if not data:
            _logger.warning(
                'ab_s3_attachment: 404 attachment id=%s name=%r key=%s — '
                'file missing in S3 and DB inline',
                self.id, self.name, self._s3_key(self.store_fname or ''),
            )
            raise NotFound()

        stream = Stream(
            mimetype=self.mimetype,
            download_name=self.name,
            etag=self.checksum,
            public=self.public,
        )
        stream.type = 'data'
        stream.data = data
        stream.size = len(data)
        return stream

    def _file_write(self, bin_value, checksum):
        """Write bytes to S3 with idempotent dedup + transient-error retry.

        Dedup safety: rely on a SQL existence check first ("does any other
        ir_attachment row already reference this checksum?"). Only then
        confirm with head_object and skip the upload — avoids dedup loss
        when a unique uploader hits a transient HEAD failure.

        Transient errors (5xx, SlowDown, RequestTimeout) get one retry
        with 1s backoff. Permanent errors (NoSuchBucket, AccessDenied,
        QuotaExceeded) raise UserError immediately.
        """
        if not self._is_s3_storage():
            return super()._file_write(bin_value, checksum)

        fname = checksum[:2] + '/' + checksum
        key = self._s3_key(fname)
        config = self._s3_config()

        # Cheap dedup pre-check: is another row already pointing at this
        # fname? (one SQL beats one S3 HEAD round-trip)
        if self._s3_dedup_skip_write(fname, key):
            return fname

        self._check_s3_quota(len(bin_value))

        last_err = None
        for attempt in (1, 2):
            try:
                self._s3_client().put_object(
                    Bucket=config['bucket'],
                    Key=key,
                    Body=bin_value,
                )
                _logger.debug(
                    'ab_s3_attachment: wrote key=%s size=%d (attempt %d)',
                    key, len(bin_value), attempt,
                )
                return fname
            except _BotoClientError as e:
                code = (e.response or {}).get('Error', {}).get('Code', '')
                last_err = e
                if code in _RETRYABLE_S3_CODES and attempt == 1:
                    _logger.warning(
                        'ab_s3_attachment: transient S3 error %s on key=%s — retrying',
                        code, key,
                    )
                    time.sleep(1)
                    continue
                _logger.error(
                    'ab_s3_attachment: S3 write failed key=%s code=%s err=%s',
                    key, code, e,
                )
                raise UserError(_('Failed to upload file to S3: %s') % str(e))
            except Exception as e:
                last_err = e
                _logger.error(
                    'ab_s3_attachment: S3 write failed key=%s err=%s',
                    key, e,
                )
                raise UserError(_('Failed to upload file to S3: %s') % str(e))

        # Belt-and-braces: shouldn't reach here, the loop returns or raises.
        raise UserError(_('Failed to upload file to S3: %s') % str(last_err))

    def _file_delete(self, fname):
        """Deferred delete via Odoo's GC checklist.

        Eagerly deleting from S3 here would wipe out files still referenced
        by other ir.attachment rows (Odoo dedups by checksum — one fname
        can back many rows). Base Odoo handles this safely by spooling
        deletes to a checklist and letting _file_gc / our
        _gc_s3_file_store decide what's actually orphaned at vacuum time.

        We defer to super() (which just touches the checklist), then let
        @api.autovacuum _gc_s3_file_store cross-check against the DB
        before any S3 DELETE.
        """
        # Always defer — even when S3 is not active, base does the right
        # thing (spool checklist for the local filestore GC).
        return super()._file_delete(fname)

    # ==================== Helpers ====================

    def _s3_dedup_skip_write(self, fname, key):
        """Return True iff we can safely skip the S3 PUT for this fname.

        Two-step check: SQL row + S3 HEAD. Both must agree, otherwise we
        upload (it's idempotent — same checksum overwrites with same bytes).
        """
        # Cheap SQL: any OTHER row already referencing this fname?
        self.env.cr.execute(
            "SELECT 1 FROM ir_attachment WHERE store_fname = %s LIMIT 1",
            (fname,),
        )
        if not self.env.cr.fetchone():
            return False

        # A row references it — confirm the S3 object is actually present.
        # If HEAD fails for any reason, do the PUT (safe, idempotent).
        try:
            self._s3_client().head_object(
                Bucket=self._s3_config()['bucket'],
                Key=key,
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
        """Garbage collect orphaned S3 objects.

        Cross-checks each S3 key against the DB before deleting — so a
        dedup-shared fname that's still referenced anywhere is NEVER
        purged. This is what makes deferred _file_delete safe.
        """
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
                fname = s3_key[len(prefix) + 1:]
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
            try:
                self._s3_client().head_object(
                    Bucket=self._s3_config()['bucket'],
                    Key=key,
                )
                migrated += 1  # already on S3
                continue
            except Exception:
                pass
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
