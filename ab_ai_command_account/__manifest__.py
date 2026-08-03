# -*- coding: utf-8 -*-
{
    'name': 'Ghaima AI Commands — Invoicing',
    'version': '18.0.1.0.0',
    'category': 'Productivity',
    'summary': '/create invoice and /create bill — draft them by typing',
    'description': """
Adds ``/create invoice`` and ``/create bill`` when Invoicing is installed.

    /create invoice partner abdalmola; date 3/8/26; items 2x latte

Both create a DRAFT account.move and stop there. Posting is a separate,
already-gated action, and that separation is the whole safety model: a
mis-read amount on a draft is an edit, on a posted entry it is a
reversal.

Restricted to the invoicing group by default, on top of the create-access
check every command performs.
    """,
    'author': 'Ghaima Tech',
    'website': 'https://ghaima.sa',
    'license': 'LGPL-3',
    'depends': ['ab_ai_command', 'account'],
    'data': ['data/ai_command_data.xml'],
    'auto_install': ['ab_ai_command', 'account'],
    'installable': True,
    'application': False,
}
