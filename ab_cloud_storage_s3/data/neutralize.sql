-- a neutralized copy must not write to the production bucket
DELETE FROM ir_config_parameter
WHERE key IN ('cloud_storage_s3_bucket_name', 'cloud_storage_s3_region', 'cloud_storage_s3_prefix',
              'cloud_storage_s3_access_key_id', 'cloud_storage_s3_secret_access_key');
