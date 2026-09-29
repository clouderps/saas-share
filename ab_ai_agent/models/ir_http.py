# -*- coding: utf-8 -*-
from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        info = super().session_info()
        user = self.env.user
        if user._is_internal():
            # One read at login, no RPC per page: the assistant decides
            # from this whether to exist, tip and listen.
            info['ai_assistant'] = user._ai_assistant_info()
        return info
