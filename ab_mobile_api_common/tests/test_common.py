import json
from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.ab_mobile_api_common.controllers import common


@tagged('post_install', '-at_install', 'ghaima_mobile_api')
class TestMobileApiCommon(TransactionCase):
    """Pure helpers of the shared mobile-API seam (no models/routes).
    Both the tenant POS API and the DBCLOUD billing API rely on this exact
    contract — response shape, CORS policy, body parsing, TTL parsing."""

    # ---- CORS policy ------------------------------------------------------
    def test_cors_headers_policy(self):
        self.assertEqual(common.CORS_HEADERS['Access-Control-Allow-Origin'], '*')
        # Credentials MUST be disabled (see module docstring/CLAUDE.md).
        self.assertEqual(common.CORS_HEADERS['Access-Control-Allow-Credentials'], 'false')
        self.assertIn('OPTIONS', common.CORS_HEADERS['Access-Control-Allow-Methods'])

    # ---- api_response -----------------------------------------------------
    def test_api_response_success_shape(self):
        resp = common.api_response(data={'x': 1})
        body = json.loads(resp.get_data(as_text=True))
        self.assertTrue(body['success'])
        self.assertEqual(body['data'], {'x': 1})
        self.assertNotIn('error', body)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get('Access-Control-Allow-Origin'), '*')

    def test_api_response_error_shape(self):
        resp = common.api_response(error='nope', code='E_AUTH', status=401)
        body = json.loads(resp.get_data(as_text=True))
        self.assertFalse(body['success'])
        self.assertEqual(body['error'], 'nope')
        self.assertEqual(body['code'], 'E_AUTH')
        self.assertEqual(resp.status_code, 401)

    def test_api_response_request_id_echoed(self):
        resp = common.api_response(data={}, request_id='req-123')
        body = json.loads(resp.get_data(as_text=True))
        self.assertEqual(body['request_id'], 'req-123')
        self.assertEqual(resp.headers.get('X-Request-ID'), 'req-123')

    def test_cors_preflight(self):
        resp = common.cors_preflight()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_data(as_text=True), '')
        self.assertEqual(resp.headers.get('Access-Control-Allow-Origin'), '*')

    # ---- get_request_data (body parsing) ----------------------------------
    def _mock_body(self, raw):
        m = MagicMock()
        m.httprequest.data = raw
        return m

    def test_get_request_data_plain_json(self):
        with patch.object(common, 'request', self._mock_body(b'{"a": 1}')):
            self.assertEqual(common.get_request_data(), {'a': 1})

    def test_get_request_data_jsonrpc_params_unwrapped(self):
        with patch.object(common, 'request', self._mock_body(b'{"params": {"b": 2}}')):
            self.assertEqual(common.get_request_data(), {'b': 2})

    def test_get_request_data_invalid_returns_empty(self):
        with patch.object(common, 'request', self._mock_body(b'not json')):
            self.assertEqual(common.get_request_data(), {})

    def test_get_request_data_empty_body(self):
        with patch.object(common, 'request', self._mock_body(b'')):
            self.assertEqual(common.get_request_data(), {})

    # ---- get_ttl (config parsing) -----------------------------------------
    def _mock_param(self, value):
        m = MagicMock()
        m.env.__getitem__.return_value.sudo.return_value.get_param.return_value = value
        return m

    def test_get_ttl_parses_int(self):
        with patch.object(common, 'request', self._mock_param('7200')):
            self.assertEqual(common.get_ttl('k', 3600), 7200)

    def test_get_ttl_falls_back_on_garbage(self):
        with patch.object(common, 'request', self._mock_param('not-a-number')):
            self.assertEqual(common.get_ttl('k', 3600), 3600)

    def test_default_ttls(self):
        self.assertEqual(common.DEFAULT_ACCESS_TTL, 3600)
        self.assertEqual(common.DEFAULT_REFRESH_TTL, 2592000)
