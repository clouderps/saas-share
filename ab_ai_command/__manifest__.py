# -*- coding: utf-8 -*-
{
    'name': 'Ghaima AI Commands',
    'version': '18.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Slash commands for the AI assistant — /create quote, …',
    'description': """
Ghaima AI Commands
==================

Lets a user create a business document by typing it::

    /create quote partner: abdalmola; date: 3/8/26; items: 2x latte

Only the verb is parsed deterministically. Everything after it gets a
tolerant ``key: value`` sweep, and whatever that cannot fill is left for
the agent to extract — so the same command works written as prose, in
Arabic, or dictated. The slash form is an accelerator, not a grammar.

Safety
------
* Commands create **drafts only**. Posting stays a separate, gated
  action, which is what makes a wrong extraction recoverable.
* The preview is rendered from the created record, so the user confirms
  the partner that actually matched and the total that was actually
  computed — not the text they typed.
* Barcodes match **exactly**; only a product *name* may fuzzy-match, and
  only when it returns a single hit.
* Ambiguity is a result, never resolved by picking the first row.
* Dates print in long form because ``3/8/26`` reads differently by
  locale.
* Every create runs as the requesting user, so record rules and create
  rights apply exactly as they do in the UI.

Extending
---------
Inherit ``ai.command.mixin`` on the target model and declare
``_ai_command_spec()``. Ship it in a bridge module that ``auto_install``s
with the domain app, so the command exists exactly when that app does.
    """,
    'author': 'Ghaima Tech',
    'website': 'https://ghaima.sa',
    'license': 'LGPL-3',
    'depends': ['ab_ai_agent'],
    'data': [
        'security/ir.model.access.csv',
        'data/ai_command_tool_data.xml',
        'views/ai_agent_command_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ab_ai_command/static/src/command_palette.scss',
            'ab_ai_command/static/src/command_palette.js',
            'ab_ai_command/static/src/command_palette.xml',
            'ab_ai_command/static/src/command_inherit.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
}
