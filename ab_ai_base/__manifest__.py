{
    'name': 'AI Provider Base',
    'version': '18.0.1.1.0',
    'category': 'Tools',
    'summary': 'Base AI provider configuration for OpenAI, Claude, Gemini, and local LLMs',
    'description': '''
AI Provider Base
================

Centralized AI provider configuration and service layer:
* Multi-provider support: OpenAI, Anthropic Claude, Google Gemini, Local LLM (Ollama)
* API key management per provider
* Usage tracking (requests, tokens)
* Connection testing
* Temperature, max tokens, timeout configuration
* Reusable AI service for any module (dashboard, POS, HR, etc.)
    ''',
    'author': 'AB Solutions',
    'website': 'https://www.ab-solutions.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
    ],
    'external_dependencies': {
        'python': ['requests'],
    },
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/ai_config_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
