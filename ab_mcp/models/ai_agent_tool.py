# -*- coding: utf-8 -*-
from odoo import api, fields, models

from ..services import catalog


class AIAgentTool(models.Model):
    _inherit = 'ai.agent.tool'

    mcp_available = fields.Boolean(
        string='Available over MCP', compute='_compute_mcp_available',
        search='_search_mcp_available',
        help='False for tools MCP never offers whatever the toggle says: screen-only '
             'tools, memory tools, server actions and write tools that would not '
             'ask for confirmation.')

    @api.model
    def _mcp_never_offered(self, tool):
        return (catalog.is_screen_only(tool) or not catalog._has_callable(tool)
                or not catalog.is_mcp_safe(tool))

    def _compute_mcp_available(self):
        for tool in self:
            tool.mcp_available = not self._mcp_never_offered(tool)

    def _search_mcp_available(self, operator, value):
        if operator not in ('=', '!='):
            return NotImplemented
        # Small catalogue (tens of rows): filter in Python with the same
        # predicates the MCP catalogue uses.
        ok = self.with_context(active_test=False).search([]).filtered(
            lambda t: not self._mcp_never_offered(t)).ids
        positive = (operator == '=') == bool(value)
        return [('id', 'in' if positive else 'not in', ok)]
