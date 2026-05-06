{
    'name': 'Redis Session & Bus',
    'summary': 'Store Ghaima sessions and bus notifications in Redis for multi-node HA',
    'description': """
Replaces Ghaima's filesystem session store with Redis.
Also configures Redis as the bus notification backend.

This enables:
- Multi-node deployments (load-balanced Ghaima instances)
- Session persistence across container restarts
- Shared real-time notifications across all nodes
- No user logout when routed to a different app node

Configuration via ir.config_parameter:
- ab_redis.url = redis://host:6379/0
- ab_redis.prefix = entity_5 (session key prefix for isolation)
- ab_redis.session_ttl = 86400 (session TTL in seconds, default 24h)
    """,
    'version': '18.0.1.0.0',
    'category': 'Technical',
    'author': 'Ghaima Tech',
    'license': 'LGPL-3',
    'depends': ['base', 'bus'],
    'data': [],
    'external_dependencies': {
        'python': ['redis'],
    },
    'post_init_hook': '_post_init_hook',
    'installable': True,
    'auto_install': False,
}
