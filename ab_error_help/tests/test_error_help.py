import json

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import serialize_exception
from odoo.tests import BaseCase, tagged

from odoo.addons.ab_error_help import (
    HelpAccessError,
    HelpUserError,
    HelpValidationError,
    attach_help,
    get_help,
)


@tagged("post_install", "-at_install")
class TestErrorHelp(BaseCase):

    def _serialize(self, exc):
        try:
            raise exc
        except Exception as caught:  # noqa: BLE001 -- serialize what was raised
            # Through json exactly like the JSON-RPC error response.
            return json.loads(json.dumps(serialize_exception(caught)))

    def test_is_the_core_exception(self):
        self.assertTrue(issubclass(HelpUserError, UserError))
        self.assertTrue(issubclass(HelpValidationError, ValidationError))
        self.assertTrue(issubclass(HelpValidationError, UserError))
        self.assertTrue(issubclass(HelpAccessError, AccessError))

    def test_message_unchanged(self):
        exc = HelpUserError("Boom.", code="x.boom", why="W", fix="F")
        self.assertEqual(str(exc), "Boom.")
        self.assertEqual(exc.args, ("Boom.",))
        self.assertEqual(exc.help_code, "x.boom")

    def test_serialized_payload(self):
        data = self._serialize(HelpValidationError(
            "Bad.", code="x.bad", why="Because.", fix="Do this."))
        self.assertEqual(data["arguments"], ["Bad."])
        self.assertEqual(data["message"], "Bad.")
        self.assertEqual(data["name"],
                         "odoo.addons.ab_error_help.exceptions.HelpValidationError")
        ctx = data["context"]
        # the fallback dialog when the client has no ab_error_help assets
        self.assertEqual(ctx["exception_class"], "odoo.exceptions.ValidationError")
        self.assertEqual(ctx["error_help"],
                         {"code": "x.bad", "why": "Because.", "fix": "Do this."})

    def test_help_dict_and_empty_parts(self):
        exc = HelpAccessError("No.", help={"code": "x.no", "fix": "Ask HR."})
        self.assertEqual(get_help(exc), {"code": "x.no", "fix": "Ask HR."})
        self.assertEqual(exc.context["exception_class"], "odoo.exceptions.AccessError")

    def test_code_required(self):
        with self.assertRaises(TypeError):
            HelpUserError("No code.")

    def test_attach_help_to_existing(self):
        exc = attach_help(ValidationError("Old."), code="x.old", why="Legacy.")
        self.assertIsInstance(exc, ValidationError)
        self.assertEqual(get_help(exc)["code"], "x.old")
        self.assertEqual(self._serialize(exc)["context"]["exception_class"],
                         "odoo.exceptions.ValidationError")

    def test_plain_errors_untouched(self):
        data = self._serialize(UserError("Plain."))
        self.assertEqual(data["context"], {})
        self.assertEqual(get_help(UserError("Plain.")), {})
