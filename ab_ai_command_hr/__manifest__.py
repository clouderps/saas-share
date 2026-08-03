# -*- coding: utf-8 -*-
{
    'name': 'Ghaima AI Commands — Employees',
    'version': '18.0.1.0.0',
    'category': 'Productivity',
    'summary': '/create employee — add an employee record by typing it',
    'description': """
Adds ``/create employee`` when Employees is installed.

    /create employee name: Abdullah Al Otaibi; job: Cashier; branch: Zulfi

Creates the employee record only. Contracts, payroll and salary are NOT
touched — those carry legal and financial weight and stay manual.

Because HR data is personal, the command is restricted to HR officers by
default, on top of the usual create-access check.
    """,
    'author': 'Ghaima Tech',
    'website': 'https://ghaima.sa',
    'license': 'LGPL-3',
    'depends': ['ab_ai_command', 'hr'],
    'data': ['data/ai_command_data.xml'],
    'auto_install': ['ab_ai_command', 'hr'],
    'installable': True,
    'application': False,
}
