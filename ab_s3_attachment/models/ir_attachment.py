import hashlib
import json
import logging
import re
import uuid
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

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
        # Serve downloads as a short-lived signed S3 link (Odoo's
        # cloud_storage pattern) — for every size, from 0 bytes. OFF until
        # the platform (or an admin) turns it on: no change to live tenants
        # by merely upgrading the module.
        'signed_urls': str(ICP.get_param('ab_s3.signed_urls', 'False')).lower() in ('true', '1', 'yes'),
        'signed_url_ttl': max(60, int(ICP.get_param('ab_s3.signed_url_ttl', '300') or 300)),
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
                    'ab_s3_attachment: S3 miss (%s) — served from local disk, '
                    're-uploading: key=%s', s3_err_name, key,
                )
                # Heal: the next read (and the signed link) finds it on S3.
                self._s3_heal_upload(key, disk_data)
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

        # Signed link: the browser downloads straight from S3; Odoo has
        # already checked access (this runs inside the binary controller).
        # Only when the object is really there — otherwise fall through to
        # the proxied read, which serves from local disk and heals S3.
        url_stream = self._s3_signed_stream()
        if url_stream:
            return url_stream

        data = self._file_read(self.store_fname)
        if not data and self.db_datas:
            data = self.raw

        if not data:
            # A regenerable asset bundle whose backing bytes are gone. This is
            # the normal state for a DB-cloned / template-launched tenant: the
            # inherited ir_attachment rows point at store_fnames whose S3
            # objects live under the SOURCE tenant's prefix, so this tenant
            # only ever reads a miss. Serving a permanent 404 breaks the web
            # client (OwlError, e.g. web.chartjs_lib fails to load). Purge the
            # stale row so the very next request regenerates the bundle under
            # THIS tenant's prefix.
            if self._is_regenerable_asset():
                self._purge_stale_asset()
            else:
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

    def _is_regenerable_asset(self):
        """True for compiled asset-bundle attachments — safe to drop & rebuild.

        Asset bundles are the only attachments Odoo can recreate from source
        on demand, so they are the only ones we may purge on a storage miss.
        """
        self.ensure_one()
        return (
            self.res_model == 'ir.ui.view'
            and self.res_id == 0
            and (self.url or '').startswith('/web/assets/')
        )

    def _purge_stale_asset(self):
        """Delete a stale asset-bundle row so Odoo regenerates it.

        Runs in an autonomous cursor: the caller raises NotFound immediately
        after, which rolls back the request transaction and would otherwise
        undo an ORM delete — trapping the tenant in a permanent 404 loop.
        Raw SQL (not unlink) is intentional: the S3 object is already gone, so
        there is nothing for the storage GC to clean up.
        """
        self.ensure_one()
        att_id = self.id
        _logger.warning(
            'ab_s3_attachment: asset bundle id=%s %r has no backing bytes '
            '(key=%s) — purging stale row so it regenerates under this '
            "tenant's prefix", att_id, self.name,
            self._s3_key(self.store_fname or ''),
        )
        try:
            with self.env.registry.cursor() as cr:
                cr.execute("DELETE FROM ir_attachment WHERE id = %s", (att_id,))
        except Exception:
            _logger.exception(
                'ab_s3_attachment: failed to purge stale asset %s', att_id)

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
                    # S3 recomputes the SHA-256 and rejects a corrupted body
                    ChecksumAlgorithm='SHA256',
                    **self._s3_encryption_args(),
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

    PROTECTED_KEY = '.ghaima/protected.json'   # under the tenant prefix (IAM scope)

    def _s3_encryption_args(self):
        """SSE for every write: ab_s3.encryption = AES256 (default) | aws:kms."""
        ICP = self.env['ir.config_parameter'].sudo()
        mode = ICP.get_param('ab_s3.encryption', 'AES256') or 'AES256'
        if mode == 'aws:kms':
            args = {'ServerSideEncryption': 'aws:kms'}
            if ICP.get_param('ab_s3.kms_key_id'):
                args['SSEKMSKeyId'] = ICP.get_param('ab_s3.kms_key_id')
            return args
        return {'ServerSideEncryption': 'AES256'}

    def _s3_protected_fnames(self):
        """Files referenced by retained snapshots, as published by the
        platform; None (= do not collect anything) when the list is missing,
        unreadable or marked incomplete."""
        config = self._s3_config()
        try:
            body = self._s3_client().get_object(
                Bucket=config['bucket'], Key=self._s3_key(self.PROTECTED_KEY))['Body'].read()
            data = json.loads(body)
        except Exception:
            return None
        if not data.get('complete'):
            return None
        return set(data.get('fnames') or [])

    @api.model
    def _s3_health_check(self):
        """put -> get -> SHA-256 compare -> delete a probe object.
        HEALTHY / DEGRADED (slow) / FAILED, stored in ab_s3.last_health."""
        if not self._is_s3_storage():
            return {'status': 'skipped'}
        config = self._s3_config()
        key = self._s3_key(f'.ghaima/healthcheck/{uuid.uuid4().hex}')
        payload = uuid.uuid4().bytes * 64
        started = time.monotonic()
        try:
            client = self._s3_client()
            client.put_object(Bucket=config['bucket'], Key=key, Body=payload,
                              ChecksumAlgorithm='SHA256', **self._s3_encryption_args())
            got = client.get_object(Bucket=config['bucket'], Key=key)['Body'].read()
            client.delete_object(Bucket=config['bucket'], Key=key)
            elapsed = time.monotonic() - started
            ok = hashlib.sha256(got).digest() == hashlib.sha256(payload).digest()
            status = 'FAILED' if not ok else ('DEGRADED' if elapsed > 5 else 'HEALTHY')
            result = {'status': status, 'seconds': round(elapsed, 2)}
        except Exception as e:
            result = {'status': 'FAILED', 'error': type(e).__name__}
        result['checked_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        self.env['ir.config_parameter'].sudo().set_param('ab_s3.last_health', json.dumps(result))
        if result['status'] != 'HEALTHY':
            _logger.warning('ab_s3_attachment: S3 health %s', result)
        return result

    # ==================== Signed links ====================

    _S3_RESIZE_PATH = re.compile(r'/\d+x\d+(/|$)')

    def _s3_can_redirect(self):
        """Whether THIS request may be answered with a signed S3 link.

        Everything qualifies (any size) except what cannot follow a
        redirect to another origin:
          * compiled asset bundles — CSS resolves fonts/images relative to
            its own URL, which would then point at S3;
          * wkhtmltopdf — it has no TLS, so an https S3 link renders as a
            missing image in the PDF;
          * /web/image requests that ask for a resize/crop — Odoo does not
            resize a link, the browser would get the full original.
        """
        from odoo.http import request
        if not request or not getattr(request, 'httprequest', None):
            return False
        if not self._s3_config()['signed_urls'] or self._is_regenerable_asset() \
                or (self.url or '').startswith('/web/assets/'):
            return False
        http = request.httprequest
        if 'wkhtmltopdf' in (http.headers.get('User-Agent') or '').lower():
            return False
        if http.path.startswith('/web/image'):
            params = request.params or {}
            if any(params.get(k) for k in ('width', 'height', 'crop')) \
                    or self._S3_RESIZE_PATH.search(http.path):
                return False
        return True

    def _s3_signed_stream(self):
        """A 'url' Stream to a signed S3 GET link, or None to proxy instead."""
        if not self._s3_can_redirect():
            return None
        from odoo.http import request, Stream
        config = self._s3_config()
        key = self._s3_key(self.store_fname)
        try:
            client = self._s3_client()
            client.head_object(Bucket=config['bucket'], Key=key)
        except Exception:
            return None          # not on S3 (yet): proxied path serves + heals
        disposition = 'attachment' if (request.params or {}).get('download') else 'inline'
        filename = self.name or 'file'
        params = {
            'Bucket': config['bucket'],
            'Key': key,
            'ResponseContentType': self.mimetype or 'application/octet-stream',
            'ResponseContentDisposition':
                f"{disposition}; filename*=UTF-8''{quote(filename)}",
        }
        try:
            url = client.generate_presigned_url(
                'get_object', Params=params, ExpiresIn=config['signed_url_ttl'])
        except Exception:
            _logger.warning('ab_s3_attachment: could not sign key=%s', key, exc_info=True)
            return None
        stream = Stream(type='url', url=url, mimetype=self.mimetype,
                        download_name=self.name)
        # Browsers may reuse the redirect until shortly before it expires.
        stream.max_age = max(config['signed_url_ttl'] - 10, 0)
        return stream

    # ==================== Self-healing ====================

    def _s3_heal_upload(self, key, data):
        """Best-effort re-upload of bytes found only on local disk."""
        try:
            self._s3_client().put_object(
                Bucket=self._s3_config()['bucket'], Key=key, Body=data)
            return True
        except Exception:
            _logger.warning('ab_s3_attachment: heal upload failed key=%s', key, exc_info=True)
            return False

    def _s3_listed_fnames(self):
        """store_fnames present on S3 under this tenant's prefix."""
        config = self._s3_config()
        prefix = config['prefix']
        cut = len(prefix) + 1 if prefix else 0
        found = set()
        paginator = self._s3_client().get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=config['bucket'],
                                       Prefix=f"{prefix}/" if prefix else ''):
            for obj in page.get('Contents', []):
                found.add(obj['Key'][cut:])
        return found

    @api.model
    def _s3_self_check(self, heal=True, limit=5000):
        """Every file the database references must exist on S3.

        Lists the prefix once, and for each referenced store_fname that is
        not there uploads it from local disk when the bytes still exist.
        Returns counts; called hourly by cron and by the central platform
        right after it switches this tenant's credentials.
        """
        if not self._is_s3_storage():
            return {'status': 'skipped', 'reason': 's3 not active'}
        self.env.cr.execute(
            "SELECT DISTINCT store_fname FROM ir_attachment WHERE store_fname IS NOT NULL")
        referenced = {r[0] for r in self.env.cr.fetchall()}
        try:
            on_s3 = self._s3_listed_fnames()
        except Exception as e:
            _logger.warning('ab_s3_attachment: self-check cannot list S3: %s', e)
            return {'status': 'error', 'error': type(e).__name__,
                    'referenced': len(referenced)}
        missing = sorted(referenced - on_s3)
        healed = unrecoverable = 0
        if heal:
            for fname in missing[:limit]:
                data = super(IrAttachment, self)._file_read(fname)
                if data and self._s3_heal_upload(self._s3_key(fname), data):
                    healed += 1
                elif not data:
                    unrecoverable += 1
        result = {
            'status': 'ok',
            'referenced': len(referenced),
            'on_s3': len(on_s3 & referenced),
            'missing': len(missing),
            'healed': healed,
            'unrecoverable': unrecoverable,
            'checked_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        }
        self.env['ir.config_parameter'].sudo().set_param(
            'ab_s3.last_self_check', repr(result))
        if missing:
            _logger.info('ab_s3_attachment: self-check %s', result)
        return result

    @api.model
    def _cron_s3_self_check(self):
        self._s3_health_check()
        self._s3_self_check(heal=True)

    # ── Remote entry points (central platform, XML-RPC) ────────
    # Odoo refuses to run methods starting with "_" over RPC, so the
    # platform's call to _s3_migrate_local_to_s3 never ran: every new
    # tenant kept its pre-S3 files on container disk only. These public
    # wrappers are what the platform calls; administrators only.

    def _s3_require_admin(self):
        from odoo.exceptions import AccessError
        if not self.env.user._is_system():
            raise AccessError(_('Only administrators can run S3 maintenance.'))

    @api.model
    def s3_migrate_local_to_s3(self):
        self._s3_require_admin()
        return self.sudo()._s3_migrate_local_to_s3()

    @api.model
    def s3_self_check(self, heal=True):
        self._s3_require_admin()
        return self.sudo()._s3_self_check(heal=bool(heal))

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

        # Same guard as Odoo's own filestore GC: block new attachment rows
        # while we read the reference list, so a file written by a
        # transaction that has not committed yet is never judged orphaned.
        # Snapshots are DB dumps that still point at these objects. The
        # platform publishes the files every retained snapshot references;
        # without a complete list nothing is collected (a deleted object
        # would make that snapshot unrestorable).
        protected = self._s3_protected_fnames()
        if protected is None:
            _logger.warning('S3 GC paused: no complete snapshot protection list for %s', prefix)
            return
        self.env.cr.execute("LOCK ir_attachment IN SHARE MODE")
        self.env.cr.execute(
            "SELECT store_fname FROM ir_attachment WHERE store_fname IS NOT NULL"
        )
        db_fnames = set(row[0] for row in self.env.cr.fetchall()) | protected
        # …and never touch an object inside the deletion grace period: an
        # upload whose row is still being created must survive, and a file
        # deleted today can still be brought back.
        grace = int(self.env['ir.config_parameter'].sudo().get_param('ab_s3.gc_grace_days', '7') or 7)
        min_age = datetime.now(timezone.utc) - timedelta(days=max(grace, 1))

        # List all S3 objects under prefix
        paginator = client.get_paginator('list_objects_v2')
        to_delete = []
        for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/"):
            for obj in page.get('Contents', []):
                s3_key = obj['Key']
                fname = s3_key[len(prefix) + 1:]
                modified = obj.get('LastModified')
                if modified and modified > min_age:
                    continue
                if fname and fname not in db_fnames and not fname.startswith('.'):
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

        # ir.attachment._search injects an implicit ('res_field', '=', False)
        # which HIDES field attachments (e.g. payment.method/res.partner images)
        # from a plain search — they are the bulk of a fresh tenant's filestore.
        # Mention res_field explicitly so that filter is NOT injected, otherwise
        # the migration silently skips them (only non-field attachments migrate).
        attachments = self.search([
            '&', ('store_fname', '!=', False),
            '|', ('res_field', '=', False), ('res_field', '!=', False),
        ])
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
