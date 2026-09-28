"""User errors that carry a help code, a "why" and a "how to fix".

How the data reaches the browser
--------------------------------
``odoo.http.serialize_exception`` (Odoo 18) sends ``exception.context``
verbatim as ``error.data.context``. We put two keys there:

* ``exception_class`` -- the *core* class name (``odoo.exceptions.UserError``
  ...). The web client's ``rpcErrorHandler`` falls back to it when the real
  class name (``odoo.addons.ab_error_help.exceptions.HelpUserError``) is not
  in the ``error_dialogs`` registry, so even a client without this module's
  assets still opens the normal warning dialog, never a traceback dialog.
* ``error_help`` -- ``{"code", "why", "fix"}``, read by the dialog patch in
  ``static/src/error_help``.

``exception.args`` stays ``(message,)`` so ``str(exc)``, logs, mobile API
envelopes and ``WarningDialog`` (which shows ``data.arguments[0]``) see
exactly the message they saw before. Nothing in core is edited or patched.
"""
from odoo.exceptions import AccessError, UserError, ValidationError

#: Key under ``exception.context`` holding the help payload.
HELP_KEY = "error_help"


def _payload(code, why, fix, help):
    data = dict(help or {})
    if code is not None:
        data["code"] = code
    if why is not None:
        data["why"] = why
    if fix is not None:
        data["fix"] = fix
    if not data.get("code"):
        raise TypeError("an error with help needs a help code")
    # Plain str: lazy translations or markup must not reach json.dumps.
    return {k: str(v) for k, v in data.items() if v}


def attach_help(exception, code=None, why=None, fix=None, help=None):
    """Attach help to an existing exception instance and return it.

    For code that receives an exception it did not build (a re-raise, a
    helper that returns an error)::

        raise attach_help(UserError(msg), code="x.y", why=..., fix=...)
    """
    base = type(exception)
    for klass in (ValidationError, AccessError, UserError):
        if isinstance(exception, klass):
            base = klass
            break
    context = dict(getattr(exception, "context", None) or {})
    context.setdefault("exception_class", f"{base.__module__}.{base.__name__}")
    context[HELP_KEY] = _payload(code, why, fix, help)
    exception.context = context
    return exception


def get_help(exception):
    """The ``{"code", "why", "fix"}`` dict of an exception, or ``{}``.

    Tests use it to assert the help code of a raised error::

        with self.assertRaises(UserError) as cm:
            settlement.action_submit()
        self.assertEqual(get_help(cm.exception)["code"],
                         "hr.settlement.submit_not_draft")
    """
    return dict((getattr(exception, "context", None) or {}).get(HELP_KEY) or {})


class _HelpMixin:
    """Shared constructor: ``(message, code=, why=, fix=, help=)``."""

    def __init__(self, message, code=None, why=None, fix=None, help=None):
        super().__init__(message)
        attach_help(self, code=code, why=why, fix=fix, help=help)

    @property
    def help_code(self):
        return get_help(self).get("code")


class HelpUserError(_HelpMixin, UserError):
    """A :class:`~odoo.exceptions.UserError` with help."""


class HelpValidationError(_HelpMixin, ValidationError):
    """A :class:`~odoo.exceptions.ValidationError` with help (constraints)."""


class HelpAccessError(_HelpMixin, AccessError):
    """An :class:`~odoo.exceptions.AccessError` with help (missing role)."""
