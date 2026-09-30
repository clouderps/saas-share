# -*- coding: utf-8 -*-
"""query_data: any readable model, as the user, validated, bounded."""
from datetime import date

from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.ab_ai_agent.services.query_data import query_data


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestQueryData(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'sale.order' not in cls.env:
            cls.skipTest(cls, 'sale not installed')
        own = 'sales_team.group_sale_salesman'
        cls.alice = new_test_user(cls.env, login='qd_alice', groups=f'base.group_user,{own}')
        cls.bob = new_test_user(cls.env, login='qd_bob', groups=f'base.group_user,{own}')
        cls.p1 = cls.env['res.partner'].create({'name': 'QD Customer One'})
        cls.p2 = cls.env['res.partner'].create({'name': 'QD Customer Two'})
        product = cls.env['product.product'].create({'name': 'QD Product', 'list_price': 100})

        def so(partner, user, qty, when):
            order = cls.env['sale.order'].create({
                'partner_id': partner.id, 'user_id': user.id, 'date_order': when,
                'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': qty,
                                       'price_unit': 100})]})
            order.action_confirm()
            order.date_order = when
            return order
        cls.a1 = so(cls.p1, cls.alice, 1, '2031-03-05 10:00:00')
        cls.a2 = so(cls.p2, cls.alice, 4, '2031-03-20 10:00:00')
        cls.a0 = so(cls.p1, cls.alice, 2, '2031-02-10 10:00:00')
        cls.b1 = so(cls.p1, cls.bob, 50, '2031-03-06 10:00:00')

    def q(self, user, **kw):
        return query_data(self.env(user=user), **kw)

    def test_totals_follow_record_rules(self):
        base = dict(model='sale.order', measures=['amount_untaxed:sum', 'count'],
                    domain=[['id', 'in', (self.a1 | self.a2 | self.a0 | self.b1).ids]])
        alice = self.q(self.alice, **base)
        kpis = alice['render']['blocks'][0]['items']
        self.assertEqual(kpis[0]['value'], '700.00')          # 100 + 400 + 200, not Bob's 5000
        self.assertEqual(kpis[1]['value'], '3')

    def test_group_by_partner_ranks_desc(self):
        res = self.q(self.alice, model='sale.order', measures=['amount_untaxed:sum'],
                     group_by=['partner_id'],
                     domain=[['id', 'in', (self.a1 | self.a2 | self.a0).ids]])
        rows = res['render']['blocks'][0]['rows']
        self.assertEqual(rows[0][0], 'QD Customer Two')        # 400 before 300
        self.assertEqual(rows[0][1], '400.00')

    def test_group_by_month_and_date_range(self):
        res = self.q(self.alice, model='sale.order', measures=['count'], group_by=['date_order:month'],
                     domain=[['id', 'in', (self.a1 | self.a2 | self.a0).ids]],
                     date_from='2031-01-01', date_to='2031-12-31')
        rows = res['render']['blocks'][0]['rows']
        self.assertEqual([r[1] for r in rows], ['1', '2'])     # Feb 1, Mar 2 (chronological)
        self.assertEqual(res['render']['blocks'][1]['type'], 'chart')

    def test_compare_previous_period(self):
        res = self.q(self.alice, model='sale.order', measures=['amount_untaxed:sum'],
                     domain=[['id', 'in', (self.a1 | self.a2 | self.a0).ids]],
                     date_from='2031-03-01', date_to='2031-03-28', compare_previous=True)
        item = res['render']['blocks'][0]['items'][0]
        self.assertEqual(item['value'], '500.00')
        self.assertEqual(item['delta_pct'], '+150.0%')          # vs 200 in the 28 days before

    def test_bad_input_is_refused_or_ignored(self):
        res = self.q(self.alice, model='sale.order', measures=['password:sum', 'name:sum'],
                     group_by=['x; drop', 'amount_total'])
        self.assertEqual(res['render']['blocks'][0]['items'][0]['label'], 'Count')
        res = self.q(self.alice, model='sale.order', domain=[['nope', '=', 1]])
        self.assertEqual(res['error'], 'invalid filter')
        res = self.q(self.alice, model='ir.config_parameter')
        self.assertEqual(res['error'], 'not permitted')

    def test_defaults_to_the_screen_model(self):
        env = self.env(user=self.alice, context={'ai_screen': {'model': 'sale.order'}})
        res = query_data(env, measures=['count'])
        self.assertIn('render', res)
