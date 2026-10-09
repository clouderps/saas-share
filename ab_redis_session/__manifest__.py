{
    'name': 'Redis Sessions',
    'summary': 'Store Ghaima sessions in Redis for multi-node HA',
    'description': """
Replaces Ghaima's filesystem session store with Redis.
Users stay logged in whichever app node serves them (load balancing),
and across container restarts. Notifications (bus) already work across nodes
through PostgreSQL.

Configuration in the server config file (not system parameters):
- server_wide_modules = base,web,ab_redis_session
- redis_url = redis://:<password>@host:6379/0
- redis_session_prefix = entity_5 (one per tenant)
- redis_session_ttl = 604800 (optional, default Odoo's 7 days)
    """,
    'version': '18.0.2.0.0',
    'category': 'Technical',
    'author': 'Ghaima Tech',
    'license': 'LGPL-3',
    'depends': ['base', 'bus'],
    'data': [],
    'external_dependencies': {
        'python': ['redis'],
    },
    'installable': True,
    'auto_install': False,
}
