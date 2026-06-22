# -*- coding: utf-8 -*-
"""Security regressions for the shared AI agent.

  * record_action must match a document EXACTLY (no substring ilike that
    could post the wrong invoice) and must check write access as the
    requesting user;
  * a configured provider/gateway failure must surface as an error, never
    be masked as a successful "simulation" answer.
"""
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.ab_ai_agent.services import tool_dispatcher as td
from odoo.addons.ab_ai_agent.services import llm_adapter


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestRecordActionSafety(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'AI Test Co'})
        self.product = self.env['product.product'].create(
            {'name': 'AI Test Product'})

    def _so(self, ref):
        return self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'client_order_ref': ref,
            'order_line': [(0, 0, {
                'product_id': self.product.id, 'product_uom_qty': 1})],
        })

    def test_substring_reference_does_not_finalize_wrong_doc(self):
        """The fuzzy-ilike bug: 'UNIQUEREF' must NOT resolve to (and post)
        'UNIQUEREF12345'."""
        so = self._so('UNIQUEREF12345')
        res = td._builtin_record_action(self.env, reference='UNIQUEREF')
        self.assertIn('error', res)
        self.assertNotIn('action', res)        # nothing matched
        self.assertEqual(so.state, 'draft')    # not confirmed

    def test_exact_reference_resolves(self):
        so = self._so('EXACTREF98765')
        res = td._builtin_record_action(self.env, reference='EXACTREF98765')
        self.assertEqual(res.get('action', {}).get('res_id'), so.id)
        self.assertEqual(so.state, 'sale')     # exact match → confirmed

    def test_no_write_access_user_cannot_finalize(self):
        so = self._so('ACLREF55555')
        portal = self.env['res.users'].create({
            'name': 'AI Portal', 'login': 'ai_portal_test',
            'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        res = td._builtin_record_action(
            self.env(user=portal.id), reference='ACLREF55555')
        self.assertIn('error', res)
        self.assertFalse(res.get('done'))
        self.assertEqual(so.state, 'draft')    # never confirmed


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestProviderFailureSurfaced(TransactionCase):

    def test_configured_failure_raises(self):
        """An active provider that errors must raise (so the run is marked
        error), not silently degrade to a fake simulation answer."""
        with patch.object(llm_adapter, '_try_get_gateway', return_value=None), \
             patch.object(llm_adapter, '_has_active_provider', return_value=True), \
             patch.object(type(self.env['ai.provider.service']), 'call',
                          side_effect=Exception('upstream 500')):
            with self.assertRaises(llm_adapter.AiProviderError):
                llm_adapter.call_llm(
                    self.env, None, system_prompt='', user_prompt='hi')

    def test_unconfigured_still_simulates(self):
        """With nothing configured (dev box), a provider error still falls
        back to simulation — only a CONFIGURED failure is an outage."""
        with patch.object(llm_adapter, '_try_get_gateway', return_value=None), \
             patch.object(llm_adapter, '_has_active_provider', return_value=False), \
             patch.object(type(self.env['ai.provider.service']), 'call',
                          side_effect=Exception('boom')):
            resp, usage, routed = llm_adapter.call_llm(
                self.env, None, system_prompt='', user_prompt='hi')
        self.assertEqual(routed, 'sim')
        self.assertTrue(usage.get('simulated'))
