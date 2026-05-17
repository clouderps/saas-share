# -*- coding: utf-8 -*-
{
    'name': 'AB AI UI — Shared response renderer',
    'version': '18.0.1.2.0',
    'category': 'Tools',
    'summary': 'OWL <AiResponse/> + block kit (KPI grid, highlight list, '
               'data table, callout, actions, tool trace, provenance) used by '
               'every AI surface (chatbot, daily report, dashboards, scan-docs)',
    'description': """
AB AI UI
========
Phase A of SAAS_AI_UI_PLAN.md. One OWL renderer shared across every AI
surface in the platform.

Consumers
---------
* ab_ai_chatbot, ab_ai_client (daily report), ab_ghaima_basic/advanced/professional
  (dashboards), ab_scan_docs, and any custom feature that calls the AI gateway.

Components
----------
* AiResponse — main entry point, switches layout based on envelope.render.layout
* Block kit:
    - AiText
    - KpiGrid (+ KpiTile)
    - HighlightList
    - DataTable
    - CalloutCard
    - AiActionButton
    - ToolTrace          (Phase F — collapsible tool-call history)
* Support:
    - SkeletonShimmer    (streaming placeholder)
    - ProvenanceBar      (model / cost / tokens / redaction / fallback footer)
    - ErrorEnvelope      (consistent error surface)

Styling uses the Ghaima design tokens from ab_ghaima_theme — never hardcoded
colours. RTL-first via CSS logical properties.
    """,
    'author': 'CloudERPs',
    'website': 'https://clouderps.com',
    'license': 'LGPL-3',
    'depends': [
        'web',
    ],
    'assets': {
        'web.assets_backend': [
            'ab_ai_ui/static/src/ai_response_components.scss',
            'ab_ai_ui/static/src/support/skeleton_shimmer.js',
            'ab_ai_ui/static/src/support/skeleton_shimmer.xml',
            'ab_ai_ui/static/src/support/error_envelope.js',
            'ab_ai_ui/static/src/support/error_envelope.xml',
            'ab_ai_ui/static/src/support/provenance_bar.js',
            'ab_ai_ui/static/src/support/provenance_bar.xml',
            'ab_ai_ui/static/src/blocks/ai_text.js',
            'ab_ai_ui/static/src/blocks/ai_text.xml',
            'ab_ai_ui/static/src/blocks/ai_markdown.js',
            'ab_ai_ui/static/src/blocks/ai_markdown.xml',
            'ab_ai_ui/static/src/blocks/suggestion_chips.js',
            'ab_ai_ui/static/src/blocks/suggestion_chips.xml',
            'ab_ai_ui/static/src/blocks/kpi_grid.js',
            'ab_ai_ui/static/src/blocks/kpi_grid.xml',
            'ab_ai_ui/static/src/blocks/highlight_list.js',
            'ab_ai_ui/static/src/blocks/highlight_list.xml',
            'ab_ai_ui/static/src/blocks/data_table.js',
            'ab_ai_ui/static/src/blocks/data_table.xml',
            'ab_ai_ui/static/src/blocks/callout_card.js',
            'ab_ai_ui/static/src/blocks/callout_card.xml',
            'ab_ai_ui/static/src/blocks/action_button.js',
            'ab_ai_ui/static/src/blocks/action_button.xml',
            'ab_ai_ui/static/src/blocks/tool_trace.js',
            'ab_ai_ui/static/src/blocks/tool_trace.xml',
            'ab_ai_ui/static/src/blocks/ai_chart.js',
            'ab_ai_ui/static/src/blocks/ai_chart.xml',
            'ab_ai_ui/static/src/ai_response/ai_response.js',
            'ab_ai_ui/static/src/ai_response/ai_response.xml',
            'ab_ai_ui/static/src/ai_response/ai_response_service.js',
            'ab_ai_ui/static/src/widgets/ai_response_envelope_widget.js',
            'ab_ai_ui/static/src/widgets/ai_response_envelope_widget.xml',
        ],
        'point_of_sale._assets_pos': [
            'ab_ai_ui/static/src/ai_response_components.scss',
            'ab_ai_ui/static/src/support/skeleton_shimmer.js',
            'ab_ai_ui/static/src/support/skeleton_shimmer.xml',
            'ab_ai_ui/static/src/support/error_envelope.js',
            'ab_ai_ui/static/src/support/error_envelope.xml',
            'ab_ai_ui/static/src/support/provenance_bar.js',
            'ab_ai_ui/static/src/support/provenance_bar.xml',
            'ab_ai_ui/static/src/blocks/ai_text.js',
            'ab_ai_ui/static/src/blocks/ai_text.xml',
            'ab_ai_ui/static/src/blocks/ai_markdown.js',
            'ab_ai_ui/static/src/blocks/ai_markdown.xml',
            'ab_ai_ui/static/src/blocks/suggestion_chips.js',
            'ab_ai_ui/static/src/blocks/suggestion_chips.xml',
            'ab_ai_ui/static/src/blocks/kpi_grid.js',
            'ab_ai_ui/static/src/blocks/kpi_grid.xml',
            'ab_ai_ui/static/src/blocks/highlight_list.js',
            'ab_ai_ui/static/src/blocks/highlight_list.xml',
            'ab_ai_ui/static/src/blocks/data_table.js',
            'ab_ai_ui/static/src/blocks/data_table.xml',
            'ab_ai_ui/static/src/blocks/callout_card.js',
            'ab_ai_ui/static/src/blocks/callout_card.xml',
            'ab_ai_ui/static/src/blocks/action_button.js',
            'ab_ai_ui/static/src/blocks/action_button.xml',
            'ab_ai_ui/static/src/blocks/tool_trace.js',
            'ab_ai_ui/static/src/blocks/tool_trace.xml',
            'ab_ai_ui/static/src/blocks/ai_chart.js',
            'ab_ai_ui/static/src/blocks/ai_chart.xml',
            'ab_ai_ui/static/src/ai_response/ai_response.js',
            'ab_ai_ui/static/src/ai_response/ai_response.xml',
            'ab_ai_ui/static/src/ai_response/ai_response_service.js',
        ],
        'web.assets_frontend': [
            'ab_ai_ui/static/src/ai_response_components.scss',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
}
