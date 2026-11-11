# -*- coding: utf-8 -*-
"""MCP prerequisites in the shared agent runtime (Phase 0).

* pending actions carry an origin; MCP ones are re-checked with the MCP
  policy (mcp.write_tools / model.allow_pii), not an agent.
* ToolPolicy callers without PII rights get masked results.
* 'mcp' usage surface and the mcp.max_calls_day feature key exist.
"""
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.ab_ai_agent.models.ai_feature_policy import FEATURES
from odoo.addons.ab_ai_agent.services import tool_dispatcher as td

LEAKY = {'name': 'Ali', 'email': 'ali@example.com',
         'lines': [{'phone': '0551234567'}, 'mail me at x@y.sa'], 'n': 5}


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestMcpPrereqs(TransactionCase):

    def test_mask_result_recurses(self):
        out = td.mask_result(self.env, LEAKY, False)
        self.assertEqual(out['name'], 'Ali')
        self.assertEqual(out['n'], 5)
        self.assertNotIn('ali@example.com', str(out))
        self.assertNotIn('0551234567', str(out))
        self.assertNotIn('x@y.sa', str(out))
        self.assertIs(td.mask_result(self.env, LEAKY, True), LEAKY)

    def _date_tool(self):
        return self.env['ai.agent.tool'].search([('code', '=', 'date_reference')], limit=1)

    def test_dispatch_masks_for_policy_without_pii(self):
        tool = self._date_tool()
        with patch.dict(td._REGISTRY, {'date_reference': lambda env, agent=None, **kw: dict(LEAKY)}):
            out = td.dispatch(self.env, tool, {}, policy=td.ToolPolicy())
            self.assertTrue(out['ok'], out)
            self.assertNotIn('ali@example.com', str(out['result']))
            out = td.dispatch(self.env, tool, {}, policy=td.ToolPolicy(allow_pii=True))
            self.assertIn('ali@example.com', str(out['result']))
            # in-app agent path is unchanged
            out = td.dispatch(self.env, tool, {}, agent=self.env['ai.agent'].get_default())
            self.assertIn('ali@example.com', str(out['result']))

    def test_surface_and_feature_key(self):
        surfaces = dict(self.env['ai.usage.local.log']._fields['surface'].selection)
        self.assertIn('mcp', surfaces)
        self.assertEqual(FEATURES['mcp.max_calls_day'][0], 'limit')
        self.assertEqual(self.env['ai.feature.policy'].get('mcp.max_calls_day'), 0)

    def _propose(self, origin=None):
        Pending = self.env['ai.agent.pending.action']
        if origin:
            Pending = Pending.with_context(ai_origin=origin)
        res = Pending.propose('date_reference', {})
        return Pending.search([('key', '=', res['confirmation']['key'])])

    def test_origin_default_and_context(self):
        self.assertEqual(self._propose().origin, 'assistant')
        self.assertEqual(self._propose('mcp').origin, 'mcp')
        self.assertEqual(self._propose('bogus').origin, 'assistant')

    def test_mcp_resolve_uses_mcp_policy(self):
        row = self._propose('mcp')
        seen = {}
        real = td.dispatch_confirmed

        def spy(env, code, args, *, agent=None, policy=None, **kw):
            seen.update(agent=agent, policy=policy)
            return real(env, code, args, agent=agent, policy=policy, **kw)
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('ab_ai_agent.feature.mcp.write_tools', 'True')
        ICP.set_param('ab_ai_agent.feature.mcp.enabled', 'True')
        Pending = self.env['ai.agent.pending.action']
        with patch.object(td, 'dispatch_confirmed', spy), \
                patch.object(type(Pending), '_mcp_origin_allowed', lambda self, row: True), \
                patch.object(type(self.env.user), '_ai_assistant_block_reason', lambda self: False):
            Pending.resolve(row.key, True)
        self.assertIsNone(seen['agent'])
        self.assertIsInstance(seen['policy'], td.ToolPolicy)
        self.assertTrue(seen['policy'].allow_write_actions)
        self.assertFalse(seen['policy'].allow_pii)

    def test_mcp_resolve_refused_without_write_tools(self):
        tool = self.env['ai.agent.tool'].search([('code', '=', 'create_record')], limit=1)
        if not tool:
            self.skipTest('create_record not present')
        self.env['ir.config_parameter'].sudo().set_param(
            'ab_ai_agent.feature.mcp.write_tools', 'False')
        row = self.env['ai.agent.pending.action'].with_context(ai_origin='mcp').propose(
            'create_record', {'model': 'res.partner', 'values': {'name': 'MCP X'}})
        out = self.env['ai.agent.pending.action'].resolve(row['confirmation']['key'], True)
        self.assertFalse(out['ok'])
        self.assertFalse(self.env['res.partner'].search_count([('name', '=', 'MCP X')]))

    def test_mcp_resolve_refused_when_mcp_off(self):
        row = self._propose('mcp')
        self.env['ir.config_parameter'].sudo().set_param('ab_ai_agent.feature.mcp.enabled', 'False')
        called = []
        with patch.object(td, 'dispatch_confirmed', lambda *a, **k: called.append(1)):
            out = self.env['ai.agent.pending.action'].resolve(row.key, True)
        self.assertFalse(out['ok'])
        self.assertFalse(called)
