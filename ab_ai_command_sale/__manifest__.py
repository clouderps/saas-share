# -*- coding: utf-8 -*-
{
    'name': 'Ghaima AI Commands — Sales',
    'version': '18.0.1.0.0',
    'category': 'Productivity',
    'summary': '/create quote — draft a quotation by typing it',
    'description': """
Adds ``/create quote`` when Sales is installed.

    /create quote partner: abdalmola; date: 3/8/26; items: 2x latte

Creates a DRAFT sale.order and shows it for confirmation. It never
confirms the order — that stays a separate, gated action.

auto_install: appears the moment both Sales and AI Commands are present,
and is absent otherwise, so no conditional code is needed anywhere.
    """,
    'author': 'Ghaima Tech',
    'website': 'https://ghaima.sa',
    'license': 'LGPL-3',
    'depends': ['ab_ai_command', 'sale'],
    'data': ['data/ai_command_data.xml'],
    'auto_install': ['ab_ai_command', 'sale'],
    'installable': True,
    'application': False,
}
