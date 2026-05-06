{
    'name': 'Mobile API Common',
    'summary': 'Shared HTTP/JWT helpers for Ghaima mobile APIs',
    'description': """
Library module: shared CORS headers, JSON response wrapper, JWT secret
accessor, TTL helpers, and request body parser used by both the
tenant-side ab_mobile_pos_api and the DBCLOUD-side
ab_mobile_saas_billing_api. No models, no views, no routes —
import-only.
    """,
    'version': '18.0.1.0.0',
    'category': 'Technical',
    'author': 'Ghaima Tech',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [],
    'external_dependencies': {
        'python': ['jwt'],
    },
    'installable': True,
    'auto_install': False,
}
