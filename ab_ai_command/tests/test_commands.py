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


@tagged('post_install', '-at_install', 'ghaima_ai_command')
class TestCreateOnConfirm(TransactionCase):
    """Search first; offer to create only when nothing matched; create
    only when the user says yes.

    Auto-creating on a miss is how a catalogue fills with "Latte",
    "latte " and "Late", and how a customer list grows a second
    "abdalmula". The offer step is what prevents that.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Command = cls.env['ai.agent.command']
        cls.quote = cls.Command.search([('code', '=', 'create_quote')], limit=1)
        cls.known = cls.env['res.partner'].create(
            {'name': 'Zzq Known Customer', 'customer_rank': 1})
        cls.product = cls.env['product.product'].create(
            {'name': 'Zzq Known Latte', 'list_price': 11.0})

    # ── existing records still win ────────────────────────────────
    def test_existing_partner_is_used_not_duplicated(self):
        before = self.env['res.partner'].search_count(
            [('name', '=', 'Zzq Known Customer')])
        res = self.quote.run({'partner_id': 'Zzq Known Customer',
                              'order_line': 'Zzq Known Latte'},
                             create_missing={'partner_id': True})
        self.assertEqual(res['status'], 'created')
        self.assertEqual(
            self.env['res.partner'].search_count(
                [('name', '=', 'Zzq Known Customer')]), before,
            'a match must never create a second record')

    # ── miss becomes an offer, not a record ───────────────────────
    def test_unknown_partner_is_offered_not_created(self):
        before = self.env['res.partner'].search_count([])
        res = self.quote.run({'partner_id': 'Zzq Brand New Person',
                              'order_line': 'Zzq Known Latte'})
        self.assertEqual(res['status'], 'needs_input')
        self.assertEqual(self.env['res.partner'].search_count([]), before,
                         'nothing may be created without an explicit yes')
        question = next(q for q in res['questions'] if q['field'] == 'partner_id')
        self.assertEqual(question['kind'], 'create_offer')
        self.assertTrue(question['can_create'])
        self.assertEqual(question['proposed']['name'], 'Zzq Brand New Person')
        self.assertIn('partner_id', res['creatable'])

    def test_unknown_product_is_offered_not_created(self):
        res = self.quote.run({'partner_id': 'Zzq Known Customer',
                              'order_line': 'Zzq Never Seen Item'})
        self.assertEqual(res['status'], 'needs_input')
        question = next(q for q in res['questions'] if q['field'] == 'order_line')
        self.assertEqual(question['kind'], 'create_offer')

    # ── confirmation creates ──────────────────────────────────────
    def test_confirming_creates_the_partner_and_the_quote(self):
        res = self.quote.run({'partner_id': 'Zzq Confirmed Person',
                              'order_line': 'Zzq Known Latte'},
                             create_missing={'partner_id': True})
        self.assertEqual(res['status'], 'created')
        partner = self.env['res.partner'].search(
            [('name', '=', 'Zzq Confirmed Person')], limit=1)
        self.assertTrue(partner)
        self.assertTrue(partner.customer_rank,
                        'created from a quote, so it is a customer')
        order = self.env['sale.order'].browse(res['id'])
        self.assertEqual(order.partner_id, partner)

    def test_confirming_creates_the_product_with_its_inline_price(self):
        res = self.quote.run({'partner_id': 'Zzq Known Customer',
                              'order_line': '3x Zzq New Pastry @ 7.5'},
                             create_missing={'order_line': True})
        self.assertEqual(res['status'], 'created')
        product = self.env['product.product'].search(
            [('name', '=', 'Zzq New Pastry')], limit=1)
        self.assertTrue(product)
        self.assertEqual(product.list_price, 7.5,
                         'a product created mid-order must not be priced 0')
        line = self.env['sale.order'].browse(res['id']).order_line
        self.assertEqual(line.product_uom_qty, 3)
        self.assertEqual(line.price_unit, 7.5)

    def test_ambiguity_is_not_a_create_offer(self):
        """Two matches means pick one, never make a third."""
        self.env['res.partner'].create(
            {'name': 'Zzq Dup Alpha', 'customer_rank': 1})
        self.env['res.partner'].create(
            {'name': 'Zzq Dup Beta', 'customer_rank': 1})
        res = self.quote.run({'partner_id': 'Zzq Dup',
                              'order_line': 'Zzq Known Latte'},
                             create_missing={'partner_id': True})
        self.assertEqual(res['status'], 'needs_input')
        question = next(q for q in res['questions'] if q['field'] == 'partner_id')
        self.assertNotEqual(question['kind'], 'create_offer')
        self.assertEqual(len(question['options']), 2)

    def test_a_failed_create_becomes_a_question_not_a_traceback(self):
        """Creating runs as the requesting user, so an access rule or a
        model constraint refusing it is a NORMAL outcome. It must come
        back as something the assistant can say out loud."""
        from unittest.mock import patch
        from odoo.exceptions import AccessError

        Sale = type(self.env['sale.order'])
        with patch.object(Sale, '_ai_command_create_missing',
                          side_effect=AccessError('nope, not allowed')):
            res = self.quote.run(
                {'partner_id': 'Zzq Refused Person',
                 'order_line': 'Zzq Known Latte'},
                create_missing={'partner_id': True})

        self.assertEqual(res['status'], 'needs_input')
        question = next(q for q in res['questions'] if q['field'] == 'partner_id')
        self.assertIn('not allowed', question['message'])
        self.assertFalse(
            self.env['res.partner'].sudo().search_count(
                [('name', '=', 'Zzq Refused Person')]))

    def test_create_runs_as_the_requesting_user(self):
        """The guarantee that matters: creation is not sudo, so it cannot
        become a way around create rights on res.partner."""
        import inspect
        source = inspect.getsource(
            type(self.env['sale.order'])._ai_command_create_missing)
        self.assertNotIn('sudo()', source,
                         'creating a missing record must never use sudo')


@tagged('post_install', '-at_install', 'ghaima_ai_command')
class TestBareValue(TransactionCase):
    """"/create invoice abdalmola" — a value with no field name.

    Reported from real use. The sweep found no pair, so the command
    reported the partner missing, which reads as the assistant being
    obtuse about something obvious.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Command = cls.env['ai.agent.command']
        cls.quote = cls.Command.search([('code', '=', 'create_quote')], limit=1)
        cls.customer = cls.env['res.partner'].create(
            {'name': 'Zzq Bare Customer', 'customer_rank': 1})

    def test_bare_value_fills_the_single_required_field(self):
        parsed, command = self.Command.parse_text(
            '/create quote Zzq Bare Customer')
        self.assertEqual(command, self.quote)
        self.assertEqual(parsed['pairs'].get('partner_id'), 'Zzq Bare Customer')

    def test_bare_value_creates_the_draft(self):
        parsed, command = self.Command.parse_text(
            '/create quote Zzq Bare Customer')
        res = command.run(parsed['pairs'])
        self.assertEqual(res['status'], 'created')
        order = self.env['sale.order'].browse(res['id'])
        self.assertEqual(order.partner_id, self.customer)

    def test_extra_whitespace_survives(self):
        """The report had a double space after the verb."""
        parsed, _c = self.Command.parse_text(
            '/create quote   Zzq Bare Customer')
        self.assertEqual(parsed['pairs'].get('partner_id'), 'Zzq Bare Customer')

    def test_explicit_key_still_wins(self):
        parsed, _c = self.Command.parse_text(
            '/create quote partner: Zzq Bare Customer; leftover words')
        self.assertEqual(parsed['pairs'].get('partner_id'), 'Zzq Bare Customer')

    def test_bare_value_still_resolves_normally(self):
        """Absorbing the leftover is not assuming it is valid — an
        unknown name must still come back as a question."""
        parsed, command = self.Command.parse_text(
            '/create quote Zzq Nobody Whatsoever')
        res = command.run(parsed['pairs'])
        self.assertEqual(res['status'], 'needs_input')

    def test_not_applied_when_two_required_fields_are_empty(self):
        """With more than one candidate there is nothing to infer, so
        the bare text must stay leftover rather than be guessed at."""
        model = self.env['sale.order']
        pairs = model._ai_command_absorb_leftover({}, 'something')
        # sale.order has exactly one required field, so this DOES fill.
        self.assertEqual(pairs.get('partner_id'), 'something')
        # …and with it already filled, nothing is overwritten.
        kept = model._ai_command_absorb_leftover(
            {'partner_id': 'first'}, 'second')
        self.assertEqual(kept['partner_id'], 'first')
