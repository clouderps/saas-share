# -*- coding: utf-8 -*-
{
    'name': 'Ghaima AI Agent — Answer Cache',
    'version': '18.0.1.0.0',
    'category': 'AI/Agents',
    'summary': 'Frequent questions answered without an LLM round-trip',
    'description': """
Remembers how the assistant answered a stand-alone question and reuses it:

* key = normalised question (Arabic tashkeel/tatweel stripped, alef/ya/ta
  marbuta folded, Arabic-Indic digits → ASCII) + company + the user's
  groups + language + agent — users with different rights never share;
* data questions replay the cached TOOL PLAN as the user (fresh numbers,
  no LLM hop), for 10 minutes; navigation / how-to answers are reused as
  is for 24 hours;
* turns that proposed or ran a write, failed a tool, or used no tool are
  never cached;
* switch: ``ab_ai_agent.answer_cache`` (default on).
    """,
    'author': 'Ghaima Tech',
    'website': 'https://ghaima.sa',
    'license': 'LGPL-3',
    'depends': ['ab_ai_agent'],
    'data': ['security/ir.model.access.csv'],
    'auto_install': True,
    'installable': True,
    'application': False,
}
