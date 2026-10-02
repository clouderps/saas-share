# -*- coding: utf-8 -*-
"""Pure unit test for the OpenAPI builder -- no DB, no Odoo env."""

import unittest

from odoo.tests import tagged
from odoo.tests.common import BaseCase

from odoo.addons.ab_api_base.lib.openapi import build_openapi_spec, _openapi_path


@tagged('post_install', '-at_install')
class TestOpenApiBuilder(BaseCase):

    def _entry(self, **kw):
        base = {
            'path': '/api/v1/pos/order/create', 'methods': ['POST'],
            'scope': 'pos', 'auth': 'token', 'summary': 'Create order',
            'description': '', 'tags': ['pos'], 'deprecated': False,
            'module': 'ab_api_pos', 'request_example': None,
            'response_example': None,
        }
        base.update(kw)
        return base

    def test_path_converter(self):
        oa, params = _openapi_path('/api/v1/pos/order/<int:oid>')
        self.assertEqual(oa, '/api/v1/pos/order/{oid}')
        self.assertEqual(params, [('oid', 'int')])

    def test_bare_path_unchanged(self):
        oa, params = _openapi_path('/api/v1/pos/order/create')
        self.assertEqual(oa, '/api/v1/pos/order/create')
        self.assertEqual(params, [])

    def test_spec_shape(self):
        spec = build_openapi_spec([self._entry()])
        self.assertEqual(spec['openapi'], '3.1.0')
        op = spec['paths']['/api/v1/pos/order/create']['post']
        self.assertEqual(op['security'], [{'bearerAuth': []}])
        self.assertEqual(op['x-scope'], 'pos')
        self.assertIn('bearerAuth', spec['components']['securitySchemes'])

    def test_public_route_has_no_security(self):
        spec = build_openapi_spec([self._entry(auth='public', scope=None)])
        op = spec['paths']['/api/v1/pos/order/create']['post']
        self.assertEqual(op['security'], [])

    def test_request_example_becomes_body(self):
        spec = build_openapi_spec([self._entry(request_example={'config_id': 1})])
        op = spec['paths']['/api/v1/pos/order/create']['post']
        self.assertEqual(
            op['requestBody']['content']['application/json']['example'],
            {'config_id': 1})

    def test_responses_ref_envelope(self):
        # ApiEnvelope must be $ref'd by responses, else codegen sees `dynamic`.
        spec = build_openapi_spec([self._entry(response_example={'success': True})])
        op = spec['paths']['/api/v1/pos/order/create']['post']
        for status in ('200', '401', '500'):
            self.assertEqual(
                op['responses'][status]['content']['application/json']['schema'],
                {'$ref': '#/components/schemas/ApiEnvelope'})
        self.assertEqual(
            op['responses']['200']['content']['application/json']['example'],
            {'success': True})


@tagged('post_install', '-at_install')
class TestApiRouteReadWrite(BaseCase):
    """Every @api_route endpoint gets a read/write cursor (see api.py)."""

    def test_routes_are_read_write(self):
        from odoo import http as odoo_http
        from odoo.addons.ab_api_base.controllers import api as api_mod
        seen = {}

        def fake_route(*args, **kwargs):
            seen.update(kwargs)
            return lambda f: f
        original = odoo_http.route
        api_mod.http.route = fake_route
        try:
            api_mod.api_route('/api/v1/test/rw', methods=('POST',), auth='public')(lambda self: None)
        finally:
            api_mod.http.route = original
            api_mod.ENDPOINT_REGISTRY[:] = [e for e in api_mod.ENDPOINT_REGISTRY if e['path'] != '/api/v1/test/rw']
        self.assertIs(seen.get('readonly'), False)
