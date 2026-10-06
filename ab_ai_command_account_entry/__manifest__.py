# -*- coding: utf-8 -*-
{
    'name': 'Ghaima AI Commands — Journal Entries',
    'version': '18.0.1.0.0',
    'category': 'Productivity',
    'summary': '"Paid rent 5000 from the bank" → a balanced DRAFT journal entry',
    'description': """
Adds the confirm-first ``create_journal_entry`` tool (قيد / قيد يومية).

The assistant turns a sentence into account / debit / credit lines; the
server resolves every account as the user, checks the entry balances in
the company currency, and only then shows a Confirm card. The entry is
created as a DRAFT (move_type = entry). Nothing here posts.
    """,
    'author': 'Ghaima Tech',
    'website': 'https://ghaima.sa',
    'license': 'LGPL-3',
    'depends': ['ab_ai_command_account'],
    'data': ['data/ai_tool_data.xml'],
    'auto_install': True,
    'installable': True,
    'application': False,
}
