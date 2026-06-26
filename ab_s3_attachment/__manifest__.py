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
    """,
    'version': '18.0.1.0.1',
    'category': 'Technical',
    'author': 'Ghaima Tech',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [],
    'external_dependencies': {
        'python': ['boto3'],
    },
    'installable': True,
    'auto_install': False,
}
