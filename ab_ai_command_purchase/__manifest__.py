# -*- coding: utf-8 -*-
{
    'name': 'Ghaima AI Commands — Purchase',
    'version': '18.0.1.0.0',
    'category': 'Productivity',
    'summary': '/create rfq — draft a purchase request by typing it',
    'description': """
Adds ``/create rfq`` when Purchase is installed.

    /create rfq vendor: Al Faisal Supplies; items: 20x flour, 5x sugar

Creates a DRAFT purchase.order (an RFQ). It never confirms the order.
    """,
    'author': 'Ghaima Tech',
    'website': 'https://ghaima.sa',
    'license': 'LGPL-3',
    'depends': ['ab_ai_command', 'purchase'],
    'data': ['data/ai_command_data.xml'],
    'auto_install': ['ab_ai_command', 'purchase'],
    'installable': True,
    'application': False,
}
