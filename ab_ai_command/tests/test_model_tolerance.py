# -*- coding: utf-8 -*-
"""What the model actually sends, found by running the assistant live.

Gemini paraphrases command codes and field names and writes Arabic
quantities; a failed create must leave nothing behind.
"""
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.ab_ai_command.services import tools
from odoo.addons.ab_ai_command.services.resolvers import split_quantity


@tagged('post_install', '-at_install', 'ghaima_ai_command')
class TestModelTolerance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Command = cls.env['ai.agent.command']
        cls.quote = cls.Command.search([('code', '=', 'create_quote')], limit=1)
        cls.product = cls.env['product.product'].create({'name': 'Zzq Tolerance Latte'})

    def test_paraphrased_code_finds_the_command(self):
        self.assertEqual(tools._closest_command(self.env, self.Command, 'create_quote_order'),
                         self.quote)
        self.assertEqual(tools._closest_command(self.env, self.Command, 'create quote'),
                         self.quote)

    def test_vague_code_is_not_guessed(self):
        self.assertFalse(tools._closest_command(self.env, self.Command, 'create'))
        self.assertFalse(tools._closest_command(self.env, self.Command, 'delete everything'))

    def test_unknown_code_returns_codes_to_retry_with(self):
        out = tools._builtin_run_command(self.env, command='zz_nothing_like_it')
        self.assertEqual(out['error'], 'no such command')
        self.assertIn('create_quote', [c['code'] for c in out['available']])

    def test_field_keys_map_through_aliases(self):
        pairs = tools._canonical_pairs(self.env, self.quote,
                                       {'customer_name': 'Acme', 'partner_id': 'B',
                                        'unknown_key': 'x'})
        # an exact spec key wins over an alias that maps to the same field
        self.assertEqual(pairs['partner_id'], 'B')
        self.assertEqual(pairs['unknown_key'], 'x')

    def test_arabic_quantities(self):
        self.assertEqual(split_quantity('قهوة موجيانا كمية 10'), (10.0, 'قهوة موجيانا'))
        self.assertEqual(split_quantity('قهوة الكمية: ١٢'), (12.0, 'قهوة'))
        self.assertEqual(split_quantity('10 حبات قهوة'), (10.0, 'قهوة'))
        self.assertEqual(split_quantity('5 pcs of sugar'), (5.0, 'sugar'))
        self.assertEqual(split_quantity('2x latte'), (2.0, 'latte'))

    def test_blocked_create_leaves_nothing_behind(self):
        Order = type(self.env['sale.order'])
        partner_count = self.env['res.partner'].search_count([])

        def create_then_fail(model, values):
            model.env['res.partner'].create({'name': 'half-made'})
            raise UserError('constraint fired after insert')
        with patch.object(Order, '_ai_command_create', create_then_fail, create=True):
            partner = self.env['res.partner'].create({'name': 'Tolerance Buyer', 'customer_rank': 1})
            out = self.quote.run({'partner_id': partner.name,
                                  'order_line': '1x Zzq Tolerance Latte'})
        self.assertEqual(out['status'], 'blocked', out)
        self.assertEqual(self.env['res.partner'].search_count([]), partner_count + 1)
        self.assertFalse(self.env['res.partner'].search([('name', '=', 'half-made')]))

    def test_dry_run_reports_a_create_that_would_fail(self):
        Order = type(self.env['sale.order'])

        def fail(model, values):
            raise UserError('no allocation')
        partner = self.env['res.partner'].create({'name': 'Dry Buyer', 'customer_rank': 1})
        with patch.object(Order, '_ai_command_create', fail, create=True):
            out = tools._dry_run(self.env, self.quote, {'partner_id': partner.name,
                                 'order_line': '1x Zzq Tolerance Latte'}, None)
        self.assertEqual(out['status'], 'blocked', out)
        self.assertIn('no allocation', out['message'])

    def test_number_first_without_x(self):
        from odoo.addons.ab_ai_command.services.resolvers import resolve_product_lines
        lines, problems = resolve_product_lines(self.env, '2 Zzq Tolerance Latte')
        self.assertFalse(problems)
        self.assertEqual((lines[0]['product_id'], lines[0]['qty']), (self.product.id, 2.0))
        named = self.env['product.product'].create({'name': '3 in 1 Zzq Coffee'})
        lines, _p = resolve_product_lines(self.env, '3 in 1 Zzq Coffee')
        self.assertEqual((lines[0]['product_id'], lines[0]['qty']), (named.id, 1.0))
