# -*- coding: utf-8 -*-
{
    'name': 'AB Reports Hub — Base',
    'version': '18.0.1.0.0',
    'category': 'Reports',
    'application': True,
    'sequence': 5,
    'summary': "Top-level Reports app icon + role groups, shared by tenant and central report bundles.",
    'description': """
AB Reports Hub — Base
=====================

Minimal kernel of the unified Reports app, shared between tenant
deployments (``ab_reports_hub`` in saas-accounting) and central
DBCLOUD deployments (``ab_reports_hub_saas`` in saas-erp/apps).

Owns:
    * Top-level "Reports" app icon (menu_reports_root)
    * Two role groups (Reports User, Reports Manager)
    * "Reports" security category
    * Implied-groups bridge for base.group_erp_manager

Does NOT own:
    * Section groups — each bundle module declares its own
    * Report records or menus — bundles reparent them
    * Hide-originals pass — only the bundle that owns the source
      menu can deactivate it
    """,
    'author': 'Abdalmola Mustafa',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/reports_groups.xml',
        'views/reports_root_menu.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'auto_install': False,
}
