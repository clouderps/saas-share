# -*- coding: utf-8 -*-
"""Regressions from the live FAYIAPROD run (2026-09-30)."""
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.ab_ai_agent.services import tool_dispatcher as td
from odoo.addons.ab_ai_agent.services.runtime import _parse_response


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestParser(TransactionCase):

    def test_final_with_raw_newlines_is_text_not_json(self):
        raw = '{"action": "final", "text": "سطر أول\nسطر ثاني"}'
        self.assertEqual(_parse_response(raw), {'kind': 'final', 'text': 'سطر أول\nسطر ثاني'})

    def test_tool_named_in_action_runs_the_tool(self):
        raw = '{"action": "open_record", "args": {"id": 7, "model": "res.partner"}, "tool_code": "open_record"}'
        self.assertEqual(_parse_response(raw),
                         {'kind': 'tool', 'tool': 'open_record', 'args': {'id': 7, 'model': 'res.partner'}})

    def test_json_after_prose_is_found(self):
        raw = 'Sure:\n{"action": "tool", "tool": "find_menu", "args": {"query": "invoice"}}'
        self.assertEqual(_parse_response(raw)['tool'], 'find_menu')

    def test_plain_prose_stays_prose(self):
        self.assertEqual(_parse_response('مرحبا')['kind'], 'final')


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestScreenDefaultsAndMenus(TransactionCase):

    def test_open_record_defaults_model_from_screen(self):
        partner = self.env['res.partner'].search([], limit=1)
        env = self.env(context=dict(self.env.context, ai_screen={'model': 'res.partner'}))
        res = td._builtin_open_record(env, id=partner.id)
        self.assertEqual(res['action']['res_model'], 'res.partner')

    def test_arabic_where_question_finds_invoice_menu(self):
        if 'account.move' not in self.env:
            self.skipTest('account not installed')
        res = td._builtin_find_menu(self.env(context=dict(self.env.context, lang='ar_001')),
                                    query='وين أسوي فاتورة عميل جديدة؟')
        self.assertTrue(res.get('matches'), res)
        self.assertTrue(any('account.move' == m['model'] for m in res['matches']), res)

    def test_screen_button_defaults_from_screen(self):
        if 'sale.order' not in self.env:
            self.skipTest('sale not installed')
        partner = self.env['res.partner'].create({'name': 'Btn Default Co'})
        product = self.env['product.product'].create({'name': 'Btn Default P'})
        so = self.env['sale.order'].create({'partner_id': partner.id, 'order_line': [
            (0, 0, {'product_id': product.id, 'product_uom_qty': 1})]})
        env = self.env(context=dict(self.env.context,
                                    ai_screen={'model': 'sale.order', 'res_id': so.id}))
        res = td._builtin_screen_button(env, button_name='Confirm')
        self.assertTrue(res.get('requires_confirmation'), res)
        self.assertEqual(so.state, 'draft')


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestAnswerShaping(TransactionCase):

    def test_render_json_after_prose_is_lifted(self):
        from odoo.addons.ab_ai_agent.services.runtime import _try_parse_report_payload
        text = ('هذه الفواتير:\n{"render": {"layout": "report", "blocks": '
                '[{"type": "data_table", "headers": ["a"], "rows": [["1"]]}]}}')
        out = _try_parse_report_payload(text)
        self.assertEqual(out['render']['blocks'][0]['type'], 'data_table')
        self.assertEqual(out['response'], 'هذه الفواتير:')

    def test_bold_html_becomes_markdown(self):
        from odoo.addons.ab_ai_agent.services.runtime import _strip_control_tokens
        self.assertEqual(_strip_control_tokens('من <b>الحسابات</b>'), 'من **الحسابات**')

    def test_prose_tables_become_data_tables(self):
        from odoo.addons.ab_ai_agent.services.runtime import _absorb_prose_table
        html = ('قبل\n<div dir="rtl"><table><thead><tr><th>العميل</th><th>المبلغ</th></tr></thead>'
                '<tbody><tr><td>أ</td><td>10</td></tr></tbody></table></div>\nبعد')
        text, block = _absorb_prose_table(html)
        self.assertEqual(block['headers'], ['العميل', 'المبلغ'])
        self.assertEqual(block['rows'], [['أ', '10']])
        self.assertNotIn('<table', text)
        md = 'x\n| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\ny'
        text, block = _absorb_prose_table(md)
        self.assertEqual(block['rows'], [['1', '2'], ['3', '4']])
        self.assertNotIn('|', text)

    def test_final_with_unescaped_quotes_is_still_text(self):
        raw = '{"action": "final", "text": "كلها في حالة "أمر البيع" الآن."}'
        self.assertEqual(_parse_response(raw),
                         {'kind': 'final', 'text': 'كلها في حالة "أمر البيع" الآن.'})
