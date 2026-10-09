{
    'name': 'Cloud Storage Amazon S3',
    'summary': 'Store chatter attachments in Amazon S3 (Odoo cloud_storage provider)',
    'description': """
Amazon S3 provider for Odoo's ``cloud_storage`` framework, the same contract
as ``cloud_storage_google`` / ``cloud_storage_azure``: large chatter and mail
attachments are uploaded by the browser straight to S3 through a short-lived
signed URL and downloaded the same way, so the file never passes through the
Odoo workers.

Credentials default to the tenant's existing ``ab_s3.*`` settings (bucket,
region, keys) and objects go under the tenant's own prefix
(``entity_<id>/cloud_storage/...``). Existing attachments are untouched.
""",
    'category': 'Technical Settings',
    'version': '18.0.1.2.0',
    'author': 'Ghaima Tech',
    'license': 'LGPL-3',
    'depends': ['cloud_storage'],
    'external_dependencies': {'python': ['boto3']},
    'data': [
        'views/settings.xml',
        'data/ir_cron.xml',
    ],
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
}
