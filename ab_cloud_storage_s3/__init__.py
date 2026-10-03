from . import models

PARAMS = ('cloud_storage_s3_bucket_name', 'cloud_storage_s3_region', 'cloud_storage_s3_prefix',
          'cloud_storage_s3_access_key_id', 'cloud_storage_s3_secret_access_key')


def uninstall_hook(env):
    ICP = env['ir.config_parameter']
    if ICP.get_param('cloud_storage_provider') == 's3':
        env['res.config.settings']._check_cloud_storage_uninstallable()
        ICP.set_param('cloud_storage_provider', False)
    ICP.search([('key', 'in', PARAMS)]).unlink()
