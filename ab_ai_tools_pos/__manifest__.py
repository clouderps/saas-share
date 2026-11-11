# -*- coding: utf-8 -*-
{
    'name': 'Ghaima AI Tools — Point of Sale',
    'version': '18.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Read-only POS tools for the AI assistant and MCP',
    'description': """
POS tool pack for the shared ``ab_ai_agent`` tool registry: session
status, top cashiers, shift summary and payment mix. Every tool runs as
the calling user (ORM + record rules, ``env.companies``), is limited to
POS users and never opens/closes sessions or takes payments.

auto_install: present whenever both the AI agent runtime and Point of
Sale are installed.
    """,
    'author': 'Ghaima Tech',
    'website': 'https://ghaima.sa',
    'license': 'LGPL-3',
    'depends': ['ab_ai_agent', 'point_of_sale'],
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
