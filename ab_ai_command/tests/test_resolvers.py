# -*- coding: utf-8 -*-
"""Resolvers decide what record a typed word means.

Two properties matter more than the rest and are tested hardest:
barcodes never fuzzy-match, and ambiguity is never resolved by picking.
"""
from datetime import date

from odoo.tests.common import TransactionCase, tagged

from ..services import resolvers


@tagged('post_install', '-at_install', 'ghaima_ai_command')
class TestPartnerResolver(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        P = cls.env['res.partner']
        cls.unique = P.create({'name': 'Zzq Unique Partner', 'customer_rank': 1})
        cls.twin_a = P.create({'name': 'Zzq Twin Alpha', 'customer_rank': 1})
        cls.twin_b = P.create({'name': 'Zzq Twin Beta', 'customer_rank': 1})
        cls.vendor = P.create({'name': 'Zzq Vendor Only', 'supplier_rank': 1})

    def test_exact_name(self):
        res = resolvers.resolve_partner(self.env, 'Zzq Unique Partner')
        self.assertEqual(res['value'], self.unique.id)
        self.assertEqual(res['confidence'], 'exact')

    def test_fuzzy_single_hit(self):
        res = resolvers.resolve_partner(self.env, 'Zzq Unique')
        self.assertEqual(res['value'], self.unique.id)
        self.assertEqual(res['confidence'], 'likely')

    def test_ambiguity_is_never_resolved_by_picking(self):
        res = resolvers.resolve_partner(self.env, 'Zzq Twin')
        self.assertIsNone(res['value'], 'must not choose between two partners')
        self.assertEqual(res['confidence'], 'ambiguous')
        self.assertEqual(len(res['alternatives']), 2)

    def test_no_match(self):
        res = resolvers.resolve_partner(self.env, 'Zzq Nobody At All')
        self.assertIsNone(res['value'])
        self.assertEqual(res['confidence'], 'none')

    def test_empty_input(self):
        self.assertIsNone(resolvers.resolve_partner(self.env, '')['value'])

    def test_wrong_role_explains_itself(self):
        """A vendor asked for as a customer is a different problem from
        "does not exist", and the fix is different too."""
        res = resolvers.resolve_partner(
            self.env, 'Zzq Vendor Only', customer=True)
        self.assertIsNone(res['value'])
        self.assertIn('not marked as a customer', res['note'])


@tagged('post_install', '-at_install', 'ghaima_ai_command')
class TestDateResolver(TransactionCase):

    def setUp(self):
        super().setUp()
        self.today = date(2026, 8, 3)

    def test_day_first_outside_en_us(self):
        self.env.user.lang = 'ar_001'
        res = resolvers.resolve_date(self.env, '3/8/26', today=self.today)
        self.assertEqual(res['value'], date(2026, 8, 3), '3/8/26 is 3 August here')

    def test_month_first_for_en_us(self):
        self.env.user.lang = 'en_US'
        res = resolvers.resolve_date(self.env, '3/8/26', today=self.today)
        self.assertEqual(res['value'], date(2026, 3, 8))

    def test_swappable_date_warns(self):
        """Both readings are valid dates, so the user must be told which
        one we took — this is the whole reason the preview prints long
        form."""
        self.env.user.lang = 'ar_001'
        res = resolvers.resolve_date(self.env, '3/8/26', today=self.today)
        self.assertEqual(res['confidence'], 'likely')
        self.assertIn('confirm', res['note'])

    def test_unswappable_date_does_not_warn(self):
        res = resolvers.resolve_date(self.env, '25/8/26', today=self.today)
        self.assertEqual(res['confidence'], 'exact')
        self.assertFalse(res['note'])

    def test_iso_is_unambiguous(self):
        res = resolvers.resolve_date(self.env, '2026-08-03', today=self.today)
        self.assertEqual(res['value'], date(2026, 8, 3))
        self.assertEqual(res['confidence'], 'exact')

    def test_four_digit_year_first(self):
        res = resolvers.resolve_date(self.env, '2026/08/03', today=self.today)
        self.assertEqual(res['value'], date(2026, 8, 3))

    def test_relative_english(self):
        self.assertEqual(
            resolvers.resolve_date(self.env, 'tomorrow', today=self.today)['value'],
            date(2026, 8, 4))

    def test_relative_arabic(self):
        for word in ('بكرة', 'غدا'):
            self.assertEqual(
                resolvers.resolve_date(self.env, word, today=self.today)['value'],
                date(2026, 8, 4), 'failed on %s' % word)

    def test_impossible_date_is_rejected(self):
        res = resolvers.resolve_date(self.env, '45/13/26', today=self.today)
        self.assertIsNone(res['value'])

    def test_garbage_is_rejected(self):
        self.assertIsNone(
            resolvers.resolve_date(self.env, 'sometime next quarter')['value'])

    def test_long_form_display(self):
        res = resolvers.resolve_date(self.env, '2026-08-03', today=self.today)
        self.assertIn('August', res['display'])


@tagged('post_install', '-at_install', 'ghaima_ai_command')
class TestProductResolver(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        P = cls.env['product.product']
        cls.exact = P.create({'name': 'Zzq Latte', 'barcode': '6281000010'})
        # A barcode that CONTAINS the other one — the fuzzy-match trap.
        cls.longer = P.create({'name': 'Zzq Latte Large',
                               'barcode': '62810000109'})
        cls.ref = P.create({'name': 'Zzq Espresso', 'default_code': 'ZZQ-ESP'})

    def test_barcode_is_exact_never_fuzzy(self):
        """Scanning 6281000010 must not land on 62810000109. A wrong item
        on an order is worse than no item."""
        res = resolvers.resolve_product(self.env, '6281000010')
        self.assertEqual(res['value'], self.exact.id)
        self.assertEqual(res['confidence'], 'exact')

    def test_the_longer_barcode_resolves_to_its_own_product(self):
        res = resolvers.resolve_product(self.env, '62810000109')
        self.assertEqual(res['value'], self.longer.id)

    def test_unknown_barcode_fails_rather_than_guessing(self):
        res = resolvers.resolve_product(self.env, '9999999999999')
        self.assertIsNone(res['value'])

    def test_internal_reference(self):
        res = resolvers.resolve_product(self.env, 'ZZQ-ESP')
        self.assertEqual(res['value'], self.ref.id)
        self.assertEqual(res['confidence'], 'exact')

    def test_exact_name_beats_the_prefix_sibling(self):
        res = resolvers.resolve_product(self.env, 'Zzq Latte')
        self.assertEqual(res['value'], self.exact.id)

    def test_ambiguous_name_returns_options(self):
        res = resolvers.resolve_product(self.env, 'Zzq Latt')
        self.assertIsNone(res['value'])
        self.assertEqual(res['confidence'], 'ambiguous')
        self.assertEqual(len(res['alternatives']), 2)

    # ── quantity parsing ──────────────────────────────────────────
    def test_quantity_forms(self):
        for text, expected in (('2x latte', (2.0, 'latte')),
                               ('2 x latte', (2.0, 'latte')),
                               ('latte x2', (2.0, 'latte')),
                               ('latte 2', (2.0, 'latte')),
                               ('2×latte', (2.0, 'latte')),
                               ('latte', (1.0, 'latte'))):
            self.assertEqual(resolvers.split_quantity(text), expected,
                             'failed on %r' % text)

    def test_decimal_quantity(self):
        self.assertEqual(resolvers.split_quantity('1.5x flour'), (1.5, 'flour'))
        self.assertEqual(resolvers.split_quantity('1,5x flour'), (1.5, 'flour'))

    # ── line resolution ───────────────────────────────────────────
    def test_lines_split_and_resolve(self):
        lines, problems = resolvers.resolve_product_lines(
            self.env, '2x Zzq Latte, ZZQ-ESP')
        self.assertEqual(len(lines), 2)
        self.assertEqual(problems, [])
        self.assertEqual(lines[0]['qty'], 2.0)

    def test_a_bad_line_does_not_reject_the_good_ones(self):
        """Rejecting the whole order because one item was mistyped makes
        the command useless — surface the one item instead."""
        lines, problems = resolvers.resolve_product_lines(
            self.env, '2x Zzq Latte, Zzq Nonexistent Thing')
        self.assertEqual(len(lines), 1)
        self.assertEqual(len(problems), 1)
        self.assertIn('Nonexistent', problems[0]['query'])

    def test_arabic_comma_splits_lines(self):
        lines, _p = resolvers.resolve_product_lines(
            self.env, 'Zzq Latte، ZZQ-ESP')
        self.assertEqual(len(lines), 2)
