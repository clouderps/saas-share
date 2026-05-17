{
    'name': 'AI Agent Runtime',
    'version': '18.0.1.9.1',
    'category': 'AI/Agents',
    'summary': 'Cross-instance AI agent runtime — personas, tools, RAG, metering. '
               'Gateway-independent: works on tenants and central DBCLOUD alike.',
    'description': '''
AI Agent Runtime
================

Phase H deliverable from SAAS_AI_PHASE_H_PLAN.md. Provides the agent
abstraction that the chatbot, chatter buttons, mail composer, and
website all share.

* ai.agent records — persona + system prompt + topic + tool catalog +
  sources + skills + cost guardrails
* Provider-agnostic ReAct run loop (services/runtime.py) — talks to the
  central gateway via ab_ai_client when present, falls back to direct
  ab_ai_base provider calls when not
* ai.usage.local.log + ai.usage.price.book — per-instance token meter
  for accurate SaaS billing, nightly reconciliation with central audit
* OWL components: <AiAgentChat/>, <AiAgentChip/>, <AiAgentSkillCard/>,
  <AiAgentTokenMeter/>, <AiAgentRunTrace/>
* Reuses the ab_ai_ui block kit renderer — single visual language
  across every AI surface

No business-domain dependencies. Vertical modules (CRM agents, POS
agents, accounting agents) layer on top via data XML + Python tools.
    ''',
    'author': 'Sala Integrated Solutions / Ghaima Tech',
    'license': 'LGPL-3',
    'depends': [
        'ab_ai_base',
        'ab_ai_ui',
        'mail',
        'bus',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        # Order matters: tools → topics (topics reference tools) → agents.
        'data/ai_agent_tool_data.xml',
        'data/ai_agent_topic_data.xml',
        'data/ai_agent_data.xml',
        'data/ai_usage_price_book_data.xml',
        'data/ir_cron_data.xml',
        'views/ai_agent_views.xml',
        'views/ai_agent_topic_views.xml',
        'views/ai_agent_skill_views.xml',
        'views/ai_agent_run_views.xml',
        'views/ai_usage_local_log_views.xml',
        'views/ai_usage_price_book_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ab_ai_agent/static/src/scss/ai_agent.scss',
            'ab_ai_agent/static/src/services/ai_agent_service.js',
            'ab_ai_agent/static/src/components/ai_agent_chat/ai_agent_chat.js',
            'ab_ai_agent/static/src/components/ai_agent_chat/ai_agent_chat.xml',
            'ab_ai_agent/static/src/components/ai_agent_chip/ai_agent_chip.js',
            'ab_ai_agent/static/src/components/ai_agent_chip/ai_agent_chip.xml',
            'ab_ai_agent/static/src/components/ai_agent_skill_card/ai_agent_skill_card.js',
            'ab_ai_agent/static/src/components/ai_agent_skill_card/ai_agent_skill_card.xml',
            'ab_ai_agent/static/src/components/ai_agent_token_meter/ai_agent_token_meter.js',
            'ab_ai_agent/static/src/components/ai_agent_token_meter/ai_agent_token_meter.xml',
            'ab_ai_agent/static/src/components/ai_agent_run_trace/ai_agent_run_trace.js',
            'ab_ai_agent/static/src/components/ai_agent_run_trace/ai_agent_run_trace.xml',
            # Chatter patch — drops "Ask AI" into every mail.thread form
            'ab_ai_agent/static/src/web/chatter_patch.js',
            'ab_ai_agent/static/src/web/chatter_patch.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
}
