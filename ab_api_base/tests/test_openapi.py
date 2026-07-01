# -*- coding: utf-8 -*-
"""Pure unit test for the OpenAPI builder -- no DB, no Odoo env."""

import unittest

from odoo.addons.ab_api_base.lib.openapi import build_openapi_spec, _openapi_path


class TestOpenApiBuilder(unittest.TestCase):

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
