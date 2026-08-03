# -*- coding: utf-8 -*-
"""Parser is a pure function — these run without touching a database.

The point of the parser is tolerance. Every test here is a real way
someone types the same command.
"""
from odoo.tests.common import TransactionCase, tagged

from ..services import parser

VERBS = ['create quote', 'create rfq', 'create employee', 'create']
ALIASES = {
    'partner': 'partner_id', 'partner name': 'partner_id',
    'customer': 'partner_id', 'عميل': 'partner_id',
    'date': 'validity_date', 'تاريخ': 'validity_date',
    'items': 'order_line', 'أصناف': 'order_line',
}


@tagged('post_install', '-at_install', 'ghaima_ai_command')
class TestParser(TransactionCase):

    # ── verb matching ─────────────────────────────────────────────
    def test_slash_is_optional(self):
        for text in ('/create quote x', 'create quote x', '  /  create quote x'):
            self.assertEqual(parser.match_verb(text, VERBS)[0], 'create quote',
                             'failed on %r' % text)

    def test_longest_verb_wins(self):
        """'create' also matches, but the specific command must win or it
        is unreachable."""
        self.assertEqual(
            parser.match_verb('/create quote for x', VERBS)[0], 'create quote')

    def test_verb_needs_a_word_boundary(self):
        """'/create quotes' must not match 'create quote' and silently
        swallow the 's'."""
        verb, _rest = parser.match_verb('/create quotes', ['create quote'])
        self.assertIsNone(verb)

    def test_unknown_verb_returns_none(self):
        self.assertIsNone(parser.match_verb('/frobnicate x', VERBS)[0])

    def test_remainder_is_stripped_of_joiners(self):
        _v, rest = parser.match_verb('/create quote: partner: x', VERBS)
        self.assertTrue(rest.startswith('partner'))

    # ── key:value sweep ───────────────────────────────────────────
    def test_the_example_from_the_brief(self):
        pairs, _left = parser.sweep_pairs(
            'partner name : abdalmola date :3/8/26; items:latte', ALIASES)
        self.assertEqual(pairs['partner_id'], 'abdalmola date :3/8/26')
        self.assertEqual(pairs['order_line'], 'latte')

    def test_semicolon_separates_pairs(self):
        pairs, _l = parser.sweep_pairs(
            'partner: abdalmola; date: 3/8/26; items: 2x latte', ALIASES)
        self.assertEqual(pairs, {
            'partner_id': 'abdalmola',
            'validity_date': '3/8/26',
            'order_line': '2x latte',
        })

    def test_newlines_separate_pairs(self):
        pairs, _l = parser.sweep_pairs(
            'partner: Acme\ndate: 2026-08-03\nitems: latte', ALIASES)
        self.assertEqual(len(pairs), 3)

    def test_padded_colons(self):
        pairs, _l = parser.sweep_pairs('date :3/8/26 ; partner :  Acme', ALIASES)
        self.assertEqual(pairs['validity_date'], '3/8/26')
        self.assertEqual(pairs['partner_id'], 'Acme')

    def test_arabic_keys(self):
        pairs, _l = parser.sweep_pairs(
            'عميل: عبدالمولى؛ تاريخ: 3/8/26', ALIASES)
        self.assertEqual(pairs.get('partner_id'), 'عبدالمولى؛ تاريخ: 3/8/26')

    def test_arabic_keys_with_semicolon(self):
        pairs, _l = parser.sweep_pairs('عميل: عبدالمولى; أصناف: لاتيه', ALIASES)
        self.assertEqual(pairs['partner_id'], 'عبدالمولى')
        self.assertEqual(pairs['order_line'], 'لاتيه')

    def test_unknown_key_is_kept_as_context(self):
        """'note: call before delivery' has no field, but dropping it
        loses information the model could use."""
        pairs, leftover = parser.sweep_pairs(
            'partner: Acme; note: call before delivery', ALIASES)
        self.assertEqual(pairs, {'partner_id': 'Acme'})
        self.assertIn('call before delivery', leftover)

    def test_free_text_becomes_leftover(self):
        pairs, leftover = parser.sweep_pairs('for Acme tomorrow', ALIASES)
        self.assertEqual(pairs, {})
        self.assertIn('Acme', leftover)

    def test_first_occurrence_wins(self):
        pairs, _l = parser.sweep_pairs(
            'partner: First; partner: Second', ALIASES)
        self.assertEqual(pairs['partner_id'], 'First')

    def test_empty_value_is_not_a_pair(self):
        pairs, leftover = parser.sweep_pairs('partner: ; items: latte', ALIASES)
        self.assertNotIn('partner_id', pairs)
        self.assertEqual(pairs['order_line'], 'latte')

    # ── key normalisation ─────────────────────────────────────────
    def test_normalise_folds_arabic_variants(self):
        self.assertEqual(parser.normalise_key('أصناف'),
                         parser.normalise_key('اصناف'))
        self.assertEqual(parser.normalise_key('Partner  Name'), 'partner name')

    def test_normalise_strips_tashkeel(self):
        self.assertEqual(parser.normalise_key('عَمِيل'), parser.normalise_key('عميل'))

    # ── full parse ────────────────────────────────────────────────
    def test_parse_returns_everything(self):
        out = parser.parse('/create quote partner: Acme; items: latte',
                           VERBS, ALIASES)
        self.assertEqual(out['verb'], 'create quote')
        self.assertEqual(out['pairs']['partner_id'], 'Acme')
        self.assertEqual(out['raw'], '/create quote partner: Acme; items: latte')

    def test_parse_without_verb_keeps_text_whole(self):
        out = parser.parse('how many sales today?', VERBS, ALIASES)
        self.assertIsNone(out['verb'])
        self.assertEqual(out['leftover'], 'how many sales today?')

    def test_looks_like_command(self):
        self.assertTrue(parser.looks_like_command('/create quote'))
        self.assertFalse(parser.looks_like_command('create quote'))
        self.assertFalse(parser.looks_like_command(''))
