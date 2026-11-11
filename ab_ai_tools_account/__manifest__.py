# -*- coding: utf-8 -*-
{
    'name': 'Ghaima AI Tools — Accounting',
    'version': '18.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Accounting tools (P&L, cash, VAT, receivables) for the AI '
               'assistant and MCP clients',
    'description': """
Accounting tool pack for the shared ``ab_ai_agent`` tool registry.

Every tool runs as the calling user through the ORM (``_read_group``):
model access, record rules and the user's allowed companies apply. Read
only; results are capped at 500 rows.

Takes over the finance tools formerly shipped inside ``ab_ai_chatbot``
(same codes) — the pre-init hook adopts the existing tool rows so the
upgrade updates them in place instead of duplicating.
    """,
    'author': 'Ghaima Tech',
    'website': 'https://ghaima.sa',
    'license': 'LGPL-3',
    'depends': ['ab_ai_agent', 'account'],
    'data': [
        'data/ai_tool_data.xml',
        'data/ai_tool_mcp_data.xml',
    ],
    'pre_init_hook': 'pre_init_hook',
    'post_init_hook': 'post_init_hook',
    'auto_install': True,
    'installable': True,
    'application': False,
}
