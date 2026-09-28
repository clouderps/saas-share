{
    "name": "Error Help",
    "summary": "Errors that explain themselves: a help code, why it happens and "
               "how to fix it, shown in the error dialog.",
    "description": """
Error Help
==========
Raise a user-facing error together with a stable help code, a one-line
"why this happens" and a "how to fix it":

    from odoo.addons.ab_error_help import HelpUserError

    raise HelpUserError(
        _("Only a draft settlement can be submitted."),
        code="hr.settlement.submit_not_draft",
        why=_("..."), fix=_("..."))

The web client's warning dialog then shows a "Why this happens" and a
"How to fix it" section under the message. A help-link provider (for
example the Knowledge Base bridge) adds an "Open guide" button that opens
the article whose code matches.

Pure infrastructure: depends on ``web`` only, adds no model, no menu and no
data. Plain ``UserError`` / ``ValidationError`` behave exactly as before.
""",
    "version": "18.0.1.0.0",
    "category": "Hidden/Tools",
    "author": "Ghaima Tech.",
    "website": "https://ghaima.sa",
    "license": "LGPL-3",
    "depends": ["web"],
    "assets": {
        "web.assets_backend": [
            "ab_error_help/static/src/error_help/*",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
