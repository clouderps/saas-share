# -*- coding: utf-8 -*-
"""End-to-end: typed text → draft document.

The rules this file exists to hold: draft only, permission-gated, and
nothing is created while a question is outstanding.
"""
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'ghaima_ai_command')
class TestCommandRegistry(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Command = cls.env['ai.agent.command']
        cls.quote = cls.Command.search([('code', '=', 'create_quote')], limit=1)

    def test_quote_command_is_installed(self):
        """The sale bridge auto-installs with Sales, so on a database
        with Sales the command must exist without anyone enabling it."""
        self.assertTrue(self.quote, 'ab_ai_command_sale should have seeded it')
        self.assertEqual(self.quote.target_model, 'sale.order')

    def test_target_must_inherit_the_mixin(self):
        from odoo.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.Command.create({
                'name': 'Bad', 'code': 'zzq_bad', 'verb': 'zzq bad',
                'target_model': 'ir.logging',      # no mixin
            })

    def test_target_must_exist(self):
        from odoo.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.Command.create({
                'name': 'Bad', 'code': 'zzq_bad2', 'verb': 'zzq bad2',
                'target_model': 'no.such.model',
            })

    def test_parse_text_finds_the_command_and_its_fields(self):
        parsed, command = self.Command.parse_text(
            '/create quote partner: Acme; items: latte')
        self.assertEqual(command, self.quote)
        self.assertEqual(parsed['pairs'].get('partner_id'), 'Acme')
        self.assertEqual(parsed['pairs'].get('order_line'), 'latte')

    def test_parse_text_ignores_a_plain_question(self):
        _parsed, command = self.Command.parse_text('how many sales today?')
        self.assertFalse(command)


@tagged('post_install', '-at_install', 'ghaima_ai_command')
class TestQuoteCommand(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Command = cls.env['ai.agent.command']
        cls.quote = cls.Command.search([('code', '=', 'create_quote')], limit=1)
        cls.customer = cls.env['res.partner'].create(
            {'name': 'Zzq Cmd Customer', 'customer_rank': 1})
        cls.twin_a = cls.env['res.partner'].create(
            {'name': 'Zzq Cmd Twin One', 'customer_rank': 1})
        cls.twin_b = cls.env['res.partner'].create(
            {'name': 'Zzq Cmd Twin Two', 'customer_rank': 1})
        cls.product = cls.env['product.product'].create(
            {'name': 'Zzq Cmd Latte', 'barcode': '7551000010',
             'list_price': 12.0})

    def _run(self, **pairs):
        return self.quote.run(pairs)

    def test_creates_a_draft(self):
        res = self._run(partner_id='Zzq Cmd Customer',
                        order_line='2x Zzq Cmd Latte')
        self.assertEqual(res['status'], 'created')
        order = self.env['sale.order'].browse(res['id'])
        self.assertEqual(order.state, 'draft', 'commands must never confirm')
        self.assertEqual(order.partner_id, self.customer)
        self.assertEqual(len(order.order_line), 1)
        self.assertEqual(order.order_line.product_uom_qty, 2)

    def test_barcode_resolves_the_line(self):
        res = self._run(partner_id='Zzq Cmd Customer', order_line='3x 7551000010')
        order = self.env['sale.order'].browse(res['id'])
        self.assertEqual(order.order_line.product_id, self.product)
        self.assertEqual(order.order_line.product_uom_qty, 3)

    def test_ambiguous_partner_creates_nothing(self):
        before = self.env['sale.order'].search_count([])
        res = self._run(partner_id='Zzq Cmd Twin', order_line='Zzq Cmd Latte')
        self.assertEqual(res['status'], 'needs_input')
        self.assertEqual(self.env['sale.order'].search_count([]), before,
                         'nothing may be created while a question is open')
        question = next(q for q in res['questions'] if q['field'] == 'partner_id')
        self.assertEqual(len(question['options']), 2)

    def test_missing_required_field_creates_nothing(self):
        res = self._run(order_line='Zzq Cmd Latte')
        self.assertEqual(res['status'], 'needs_input')
        self.assertTrue(any(q['field'] == 'partner_id' and q['kind'] == 'missing'
                            for q in res['questions']))

    def test_unknown_product_creates_nothing(self):
        res = self._run(partner_id='Zzq Cmd Customer',
                        order_line='Zzq Cmd Nonexistent')
        self.assertEqual(res['status'], 'needs_input')

    def test_swappable_date_still_creates_but_flags_it(self):
        """A date we had to interpret is not a blocker — but the user is
        told how we read it."""
        self.env.user.lang = 'ar_001'
        res = self._run(partner_id='Zzq Cmd Customer',
                        order_line='Zzq Cmd Latte', validity_date='3/8/26')
        self.assertEqual(res['status'], 'created')
        self.assertTrue(any(q['kind'] == 'confirm' for q in res['questions']))

    def test_preview_reads_back_off_the_record(self):
        """The user confirms what exists, not what they typed."""
        res = self._run(partner_id='Zzq Cmd Customer',
                        order_line='2x Zzq Cmd Latte')
        preview = res['preview']
        self.assertEqual(preview['model'], 'sale.order')
        self.assertTrue(preview['lines'])
        self.assertEqual(preview['lines'][0][0], self.product.display_name)
        self.assertTrue(any('Zzq Cmd Customer' in cell
                            for row in preview['header'] for cell in row))

    def test_preview_dates_are_long_form(self):
        res = self._run(partner_id='Zzq Cmd Customer',
                        order_line='Zzq Cmd Latte', validity_date='2026-08-03')
        self.assertTrue(any('August' in cell
                            for row in res['preview']['header'] for cell in row))

    def test_dry_run_creates_nothing(self):
        before = self.env['sale.order'].search_count([])
        res = self.quote.run({'partner_id': 'Zzq Cmd Customer',
                              'order_line': 'Zzq Cmd Latte'}, dry_run=True)
        self.assertEqual(res['status'], 'dry_run')
        self.assertEqual(self.env['sale.order'].search_count([]), before)


@tagged('post_install', '-at_install', 'ghaima_ai_command')
class TestCommandPermissions(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Command = cls.env['ai.agent.command']
        cls.quote = cls.Command.search([('code', '=', 'create_quote')], limit=1)
        cls.portal = cls.env['res.users'].create({
            'name': 'Zzq Cmd Portal', 'login': 'zzq_cmd_portal',
            'groups_id': [(6, 0, [cls.env.ref('base.group_portal').id])],
        })

    def test_palette_is_scoped_to_the_user(self):
        admin = self.Command.palette_for_user(self.env.user)
        portal = self.Command.palette_for_user(self.portal)
        self.assertGreater(len(admin), len(portal))

    def test_portal_user_cannot_see_the_quote_command(self):
        self.assertFalse(self.quote.available_for(self.portal))

    def test_running_without_permission_is_blocked(self):
        res = self.quote.with_user(self.portal).run(
            {'partner_id': 'anyone', 'order_line': 'anything'})
        self.assertEqual(res['status'], 'blocked')

    def test_blocked_run_creates_nothing(self):
        before = self.env['sale.order'].search_count([])
        self.quote.with_user(self.portal).run({'partner_id': 'x'})
        self.assertEqual(self.env['sale.order'].search_count([]), before)
