# -*- coding: utf-8 -*-
{
    'name': 'Ghaima AI Tools — Sales',
    'version': '18.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Read-only sales tools for the AI assistant and MCP',
    'description': """
Sales tool pack for the shared ``ab_ai_agent`` tool registry: headline
totals, top products, top customers, sales by branch and the monthly
trend. Every tool aggregates through the ORM as the calling user
(``_read_group``: ACLs, record rules, ``env.companies``), is limited to
salespeople and returns at most 500 rows. Point of Sale orders are
included when that app is installed and readable by the user.

auto_install: present whenever both the AI agent runtime and Sales are
installed.
    """,
    'author': 'Ghaima Tech',
    'website': 'https://ghaima.sa',
    'license': 'LGPL-3',
    'depends': ['ab_ai_agent', 'sale'],
    'data': [
        'data/ai_tool_data.xml',
        'data/ai_tool_mcp_defaults.xml',
    ],
    'pre_init_hook': 'pre_init_hook',
    'post_init_hook': 'post_init_hook',
    'auto_install': True,
    'installable': True,
    'application': False,
}
