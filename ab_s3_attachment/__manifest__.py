{
    'name': 'S3 Attachment Storage',
    'summary': 'Store Ghaima filestore attachments on AWS S3',
    'description': """
Redirects ir.attachment file storage to AWS S3.
Configured via ir.config_parameter (injected by SaaS management platform).

Required ir.config_parameter keys:
- ir_attachment.location = 's3'
- ab_s3.bucket = 'bucket-name'
- ab_s3.prefix = 'entity_5/filestore'
- ab_s3.region = 'us-east-1'
- ab_s3.access_key_id = 'AKIA...'
- ab_s3.secret_access_key = '...'
- ab_s3.max_storage_bytes = 0 (0 = unlimited)
- ab_s3.signed_urls = False by default (True: downloads redirect to a signed S3 link)
- ab_s3.signed_url_ttl = 300 (seconds)

Downloads of every size are answered with a short-lived signed S3 link
after Odoo's own access check (asset bundles, wkhtmltopdf and resized
images stay proxied). A file missing on S3 is served from local disk and
re-uploaded; an hourly job (inactive by default) verifies every referenced
file is on S3.
    """,
    'version': '18.0.1.2.0',
    'category': 'Technical',
    'author': 'Ghaima Tech',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': ['data/ir_cron.xml'],
    'external_dependencies': {
        'python': ['boto3'],
    },
    'installable': True,
    'auto_install': False,
}
