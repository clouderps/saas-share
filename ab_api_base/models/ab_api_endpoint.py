# -*- coding: utf-8 -*-
"""Backend mirror of this server's live API surface.

`action_refresh` rebuilds the list from the same source the Swagger spec uses
(`collect_endpoints`) — the live routing map + @api_route registry + register_doc
overlays. Instance-scoped: on a tenant it lists tenant APIs, on the central
server it lists central APIs.
"""

from odoo import api, fields, models


class AbApiEndpoint(models.Model):
    _name = 'ab.api.endpoint'
    _description = 'API Endpoint'
    _order = 'tag, path'
    _rec_name = 'path'

    path = fields.Char(required=True, index=True)
    http_methods = fields.Char(string='Methods')
    tag = fields.Char(string='Group')
    scope = fields.Char()
    auth_mode = fields.Char(string='Auth')
    is_public = fields.Boolean(string='Public')
    module = fields.Char()
    summary = fields.Char()
    description = fields.Text()

    # NOT @api.model: this is a list-view header button, and
    # /web/dataset/call_button always sends the selected ids as args[0].
    # call_kw only strips that leading element for methods without an
    # `_api` marker, so an @api.model view button raises
    # "takes 1 positional argument but 2 were given". The post_init
    # hook call in __init__.py still works — it runs on an empty
    # recordset, which this method never reads.
    def action_refresh(self):
        """Rebuild the list from this server's live API surface, then open it."""
        from odoo.addons.ab_api_base.controllers.docs import collect_endpoints
        entries = collect_endpoints(self.env)
        open_list = {
            'type': 'ir.actions.act_window',
            'name': 'API Endpoints',
            'res_model': 'ab.api.endpoint',
            'view_mode': 'list,form',
            'target': 'current',
        }
        # The werkzeug routing map is only built inside an HTTP request; in a
        # non-HTTP context (post_init / shell) collect_endpoints is empty — do
        # NOT wipe an already-populated list in that case.
        if not entries:
            return open_list
        self.sudo().search([]).unlink()
        vals = []
        for e in entries:
            methods = [m for m in (e.get('methods') or []) if m != 'OPTIONS']
            vals.append({
                'path': e['path'],
                'http_methods': ', '.join(methods) or 'POST',
                'tag': (e.get('tags') or ['default'])[0],
                'scope': e.get('scope') or '',
                'auth_mode': e.get('auth') or '',
                'is_public': e.get('auth') == 'public',
                'module': e.get('module') or '',
                'summary': e.get('summary') or '',
                'description': e.get('description') or '',
            })
        if vals:
            self.sudo().create(vals)
        return open_list
