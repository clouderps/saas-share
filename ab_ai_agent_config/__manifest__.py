# -*- coding: utf-8 -*-
{
    'name': 'Ghaima AI Agent — Settings',
    'version': '18.0.1.0.0',
    'category': 'AI/Agents',
    'summary': '"Turn on multi-currency" — whitelisted settings, changed only after Confirm',
    'description': """
Lets the assistant change a short, whitelisted set of settings:

* each option maps to one ``res.config.settings`` field (boolean,
  selection or many2one) and is offered only when that field exists;
* the assistant proposes an old → new card; on Confirm the settings
  wizard runs ``execute()`` AS THE USER, so only administrators can
  apply it (plus the option's own group when set);
* ``ir.config_parameter`` is never touched.
    """,
    'author': 'Ghaima Tech',
    'website': 'https://ghaima.sa',
    'license': 'LGPL-3',
    'depends': ['ab_ai_agent'],
    'data': [
        'security/ir.model.access.csv',
        'data/ai_setting_option_data.xml',
        'data/ai_tool_data.xml',
        'views/ai_agent_setting_option_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'application': False,
}
