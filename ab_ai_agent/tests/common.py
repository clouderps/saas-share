# -*- coding: utf-8 -*-
"""Shared test helpers.

The suite also has to pass on a real tenant database, where optional
isolation layers this module knows nothing about are installed (multi-
branch: a user with no branch sees no branch-scoped record). The helper
only looks at field names, so nothing here depends on those modules.
"""
from odoo.tests.common import new_test_user as _new_test_user


def tenant_ready(user):
    """Give a test user what optional isolation layers require."""
    if 'branch_ids' in user._fields and 'res.branch' in user.env:
        # sudo: fixture setup, the branch list is admin-only.
        branches = user.env['res.branch'].sudo().search([])
        if branches:
            vals = {'branch_ids': [(6, 0, branches.ids)]}
            if 'default_branch_id' in user._fields:
                vals['default_branch_id'] = branches[0].id
            user.sudo().write(vals)
    return user


def new_test_user(env, login='', groups='base.group_user', context=None, **kwargs):
    return tenant_ready(_new_test_user(env, login=login, groups=groups,
                                       context=context, **kwargs))
