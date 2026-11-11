# -*- coding: utf-8 -*-
"""Install hooks shared by the ``ab_ai_tools_<area>`` tool packs."""
import logging

_logger = logging.getLogger(__name__)

ASSISTANT_XMLID = 'ab_ai_agent.agent_ghaima_assistant'


def adopt_tool_rows(env, module, code_to_name):
    """Bind existing ``ai.agent.tool`` rows (created without an xmlid by
    ab_ai_chatbot's sync) to the pack's xmlids, so loading the pack's XML
    updates them instead of failing on UNIQUE(code).

    Language copies that merely repeat the English text (what the sync
    wrote) are dropped so the pack's ar.po loads; a real translation an
    admin entered is kept. Raw SQL: the ORM has no per-language delete
    for jsonb translated fields.
    """
    Tool = env['ai.agent.tool'].with_context(active_test=False)
    Data = env['ir.model.data']
    for code, name in code_to_name.items():
        tool = Tool.search([('code', '=', code)], limit=1)
        if not tool or Data.search_count([('module', '=', module), ('name', '=', name)]):
            continue
        Data.create({'module': module, 'name': name, 'model': 'ai.agent.tool',
                     'res_id': tool.id, 'noupdate': False})
        for col in ('name', 'description'):
            env.cr.execute(f"""
                UPDATE ai_agent_tool t SET {col} = (
                    SELECT jsonb_object_agg(e.key, e.value) FROM jsonb_each(t.{col}) e
                    WHERE e.key = 'en_US' OR e.value IS DISTINCT FROM t.{col}->'en_US')
                WHERE t.id = %s AND t.{col} IS NOT NULL""", (tool.id,))
        tool.invalidate_recordset(['name', 'description'])
        _logger.info("Adopted ai.agent.tool %s (id %s) as %s.%s", code, tool.id, module, name)


def attach_to_assistant(env, module, names):
    """Offer the pack's tools to the Ghaima Assistant (link only, never
    replaces its tool list)."""
    agent = env.ref(ASSISTANT_XMLID, raise_if_not_found=False)
    if not agent:
        return
    tools = env['ai.agent.tool'].browse([
        rid for rid in (env['ir.model.data']._xmlid_to_res_id(f'{module}.{n}', raise_if_not_found=False)
                        for n in names) if rid])
    if tools:
        agent.write({'tool_ids': [(4, t.id) for t in tools]})
