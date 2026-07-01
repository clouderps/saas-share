# -*- coding: utf-8 -*-
"""Build an OpenAPI 3.1 spec from the endpoint registry.

Pure function of (entries, title, version) -- no Odoo imports -- so it is
unit-testable on its own (see tests/test_openapi.py).
"""

import re

# Odoo werkzeug converters -> OpenAPI param type. Also matches the bare
# `<name>` form (defaults to string).
_CONVERTER_RE = re.compile(r'<(?:(int|float|string|path|any|model|models)(?:\([^)]*\))?:)?([^>]+)>')

_TYPE_MAP = {'int': 'integer', 'float': 'number', 'path': 'string',
             'string': 'string', 'any': 'string', None: 'string'}


def _openapi_path(odoo_path):
    """'/api/v1/pos/order/<int:oid>' -> ('/api/v1/pos/order/{oid}', [(oid,int)])."""
    params = []

    def repl(m):
        conv, name = m.group(1), m.group(2)
        params.append((name, conv))
        return '{%s}' % name

    return _CONVERTER_RE.sub(repl, odoo_path), params


def _operation(entry, path_params):
    security = [] if entry['auth'] == 'public' else [{'bearerAuth': []}]
    op = {
        'summary': entry['summary'] or entry['path'],
        'tags': entry['tags'],
        'security': security,
        'x-scope': entry['scope'],
        'x-auth': entry['auth'],
        'responses': {
            '200': {'description': 'Success (envelope: {success:true, data})'},
            '401': {'description': 'Unauthenticated / invalid token'},
        },
    }
    if entry['description']:
        op['description'] = entry['description']
    if entry['deprecated']:
        op['deprecated'] = True
    if path_params:
        op['parameters'] = [{
            'name': name,
            'in': 'path',
            'required': True,
            'schema': {'type': _TYPE_MAP.get(conv, 'string')},
        } for name, conv in path_params]
    if entry['request_example'] is not None:
        op['requestBody'] = {
            'required': True,
            'content': {'application/json': {'example': entry['request_example']}},
        }
    if entry['response_example'] is not None:
        op['responses']['200']['content'] = {
            'application/json': {'example': entry['response_example']},
        }
    return op


def build_openapi_spec(entries, title='Ghaima APIs', version='1.0.0',
                       description='', server_url='/'):
    paths = {}
    tag_names = []
    for entry in entries:
        oa_path, path_params = _openapi_path(entry['path'])
        item = paths.setdefault(oa_path, {})
        for method in entry['methods']:
            if method.upper() == 'OPTIONS':
                continue
            item[method.lower()] = _operation(entry, path_params)
        for tag in entry['tags']:
            if tag not in tag_names:
                tag_names.append(tag)

    return {
        'openapi': '3.1.0',
        'info': {
            'title': title,
            'version': version,
            'description': description or 'Unified CloudERPs REST API.',
        },
        'servers': [{'url': server_url}],
        'tags': [{'name': t} for t in sorted(tag_names)],
        'paths': paths,
        'components': {
            'securitySchemes': {
                'bearerAuth': {
                    'type': 'http',
                    'scheme': 'bearer',
                    'bearerFormat': 'JWT',
                    'description': 'One token for all APIs. Obtain via '
                                   'POST /api/v1/auth/login and send as '
                                   '`Authorization: Bearer <token>`.',
                },
            },
            'schemas': {
                'ApiEnvelope': {
                    'type': 'object',
                    'properties': {
                        'success': {'type': 'boolean'},
                        'data': {'type': 'object'},
                        'error': {'type': 'string'},
                        'code': {'type': 'string'},
                        'request_id': {'type': 'string'},
                    },
                    'required': ['success'],
                },
            },
        },
    }
