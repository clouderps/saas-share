# -*- coding: utf-8 -*-
from datetime import datetime, timedelta, timezone

from odoo import api, fields, models


class McpUsageDay(models.Model):
    _name = 'mcp.usage.day'
    _description = 'Ghaima MCP — Calls per day (quota counter)'
    _order = 'day desc'

    day = fields.Date(required=True, readonly=True)
    calls = fields.Integer(readonly=True)

    _sql_constraints = [('day_unique', 'unique(day)', 'One counter per day.')]

    @api.model
    def _today(self):
        # UTC on purpose: the quota is tenant-wide, so it must roll over at
        # one instant for everybody, whatever the caller's timezone.
        return datetime.now(timezone.utc).date()

    @api.model
    def calls_today(self):
        row = self.sudo().search([('day', '=', self._today())], limit=1)
        return row.calls

    @api.model
    def _consume(self, limit):
        """Count one call; False when ``limit`` (>0) is already reached.

        Raw SQL on purpose: an atomic upsert-and-increment, so concurrent
        requests cannot both take the last call of the day. It runs on its
        own short cursor, committed at once, in READ COMMITTED: the row
        lock lasts milliseconds instead of the whole tool call, and a
        concurrent increment waits and re-reads instead of failing with a
        serialization error. A call that later fails still counts.
        """
        day = self._today()
        registry = self.env.registry
        with registry.cursor() as cr:
            if not registry.in_test_mode():
                cr.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            cr.execute("""
                INSERT INTO mcp_usage_day (day, calls, create_uid, write_uid, create_date, write_date)
                VALUES (%s, 0, 1, 1, now() at time zone 'utc', now() at time zone 'utc')
                ON CONFLICT (day) DO NOTHING
            """, [day])
            if limit:
                cr.execute("""UPDATE mcp_usage_day SET calls = calls + 1,
                                     write_date = now() at time zone 'utc'
                              WHERE day = %s AND calls < %s RETURNING calls""", [day, limit])
            else:
                cr.execute("""UPDATE mcp_usage_day SET calls = calls + 1,
                                     write_date = now() at time zone 'utc'
                              WHERE day = %s RETURNING calls""", [day])
            ok = bool(cr.fetchone())
        self.invalidate_model(['calls'])
        return ok

    @api.autovacuum
    def _gc_old_days(self):
        self.sudo().search([('day', '<', self._today() - timedelta(days=90))]).unlink()
