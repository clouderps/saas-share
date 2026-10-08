# -*- coding: utf-8 -*-
{
    'name': 'Ghaima AI Commands — Time Off',
    'version': '18.0.1.0.0',
    'category': 'Productivity',
    'summary': '/create leave — request time off for yourself by typing it',
    'description': """
Adds ``/create leave`` when Time Off is installed.

    /create leave type: Annual Leave; from: next Sunday; to: next Tuesday

Files a time-off request for the requesting user's own employee, exactly
as if they had pressed New in Time Off: allocation, overlap and Ghaima
leave rules all apply, and the request goes to the normal approval.
    """,
    'author': 'Ghaima Tech',
    'website': 'https://ghaima.sa',
    'license': 'LGPL-3',
    'depends': ['ab_ai_command', 'hr_holidays'],
    'data': ['data/ai_command_data.xml'],
    'auto_install': ['ab_ai_command', 'hr_holidays'],
    'installable': True,
    'application': False,
}
