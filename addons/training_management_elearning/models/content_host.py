from urllib.parse import urlsplit
from odoo import models
from odoo.http import request
from werkzeug.exceptions import Forbidden


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _match(cls, path_info):
        # Defence in depth: the proxy stays the first boundary of the content host.
        if not path_info.startswith('/tm-content/') and cls._is_content_host():
            raise Forbidden()
        return super()._match(path_info)

    @classmethod
    def _is_content_host(cls):
        params = request.env['ir.config_parameter'].sudo()
        content = urlsplit(params.get_str('training_elearning.content_origin', '')).netloc.lower()
        portal = urlsplit(params.get_str('training_elearning.portal_origin', '')).netloc.lower()
        # A misconfiguration naming one host twice must not lock the portal out.
        return bool(content) and content != portal and request.httprequest.host.lower() == content
