{
    'name': 'Ghaima MCP Server',
    'version': '18.0.1.1.0',
    'category': 'AI/Agents',
    'summary': 'Expose Ghaima AI tools to external AI apps (Claude, Cursor, ChatGPT…) '
               'over the Model Context Protocol, with per-user tokens.',
    'description': '''
Domain-free MCP endpoint (POST /mcp, stateless JSON-RPC 2.0). Serves the
tools of the shared ab_ai_agent registry that an operator exposed, under
the same gates as the in-app assistant (groups, record rules, plan,
kill switch). Write tools only propose: the user confirms them in the
Approvals inbox.
    ''',
    'author': 'Ghaima Team',
    'license': 'LGPL-3',
    'depends': ['ab_ai_agent'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ai_agent_tool_data.xml',
        'views/mcp_token_views.xml',
        'views/mcp_call_log_views.xml',
        'views/pending_action_views.xml',
        'views/ai_agent_tool_views.xml',
        'wizard/mcp_connect_wizard_views.xml',
        'views/res_users_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ab_mcp/static/src/scss/ab_mcp.scss',
            'ab_mcp/static/src/xml/copy_button.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
}
