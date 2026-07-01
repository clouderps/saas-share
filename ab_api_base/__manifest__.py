# -*- coding: utf-8 -*-
{
    'name': 'CloudERPs API Base',
    'version': '18.0.1.3.0',
    'category': 'Technical',
    'summary': 'Unified API seam: one token, one decorator, auto OpenAPI/Swagger docs',
    'description': """
CloudERPs API Base
==================
The single seam every ``ab_api_*`` domain module builds on:

- One ``@api_route`` decorator that replaces ``@http.route`` + a per-module
  ``@jwt_required``. It handles CORS, correlation ids, the standard JSON
  envelope, and scope-gated authentication for four trust boundaries:
    * ``token``   -- user JWT (HS256, shared ``mobile_api.jwt_secret``) with a
                     domain-registered scope validator (device, partner, ...).
    * ``service`` -- opaque bearer resolved by a registered resolver
                     (payment gateway's per-tenant hash lookup).
    * ``admin``   -- constant-time compare against a config-param token.
    * ``public``  -- no auth, optional in-process rate limiting.
- An in-process endpoint registry that generates an OpenAPI 3.1 spec
  (``/api/v1/openapi.json``) and serves Swagger UI (``/api/v1/docs``),
  filtered to the modules actually installed in the current database.

Domain modules register their scope validators / service resolvers at import
time, so this module stays free of any business-domain dependency.
    """,
    'author': 'Ghaima Tech',
    'website': 'https://ghaima.sa',
    'license': 'LGPL-3',
    'depends': [
        'ab_mobile_api_common',
    ],
    'external_dependencies': {
        'python': ['pyjwt'],
    },
    'data': [],
    'installable': True,
    'auto_install': False,
    'application': False,
}
