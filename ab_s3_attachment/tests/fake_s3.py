"""In-memory stand-in for the boto3 S3 client used by ab_s3_attachment."""
from datetime import datetime, timezone
from urllib.parse import urlencode

from botocore.exceptions import ClientError


class FakeS3:
    def __init__(self):
        self.objects = {}          # key -> [bytes, LastModified]
        self.deleted = []

    def _missing(self, key):
        return ClientError({'Error': {'Code': '404', 'Message': key}}, 'HeadObject')

    def put_object(self, Bucket, Key, Body, **kwargs):
        self.last_put_args = kwargs
        self.objects[Key] = [bytes(Body), datetime.now(timezone.utc)]

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise self._missing(Key)
        data = self.objects[Key][0]

        class _Body:
            def read(self_inner):
                return data
        return {'Body': _Body()}

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise self._missing(Key)
        return {'ContentLength': len(self.objects[Key][0])}

    def generate_presigned_url(self, op, Params, ExpiresIn):
        q = {'X-Amz-Expires': ExpiresIn,
             'response-content-disposition': Params.get('ResponseContentDisposition', ''),
             'response-content-type': Params.get('ResponseContentType', '')}
        return f"https://{Params['Bucket']}.s3.test/{Params['Key']}?{urlencode(q)}"

    def get_paginator(self, name):
        fake = self

        class _P:
            def paginate(self_inner, Bucket, Prefix=''):
                yield {'Contents': [{'Key': k, 'LastModified': v[1]}
                                    for k, v in fake.objects.items() if k.startswith(Prefix)]}
        return _P()

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)

    def delete_objects(self, Bucket, Delete):
        for o in Delete['Objects']:
            self.objects.pop(o['Key'], None)
            self.deleted.append(o['Key'])
