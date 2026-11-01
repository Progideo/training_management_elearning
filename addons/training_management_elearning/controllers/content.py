import html
import json
import mimetypes
from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError, ValidationError
from werkzeug.exceptions import Forbidden, NotFound
from ..services.archive import safe_path


def origin():
    return request.httprequest.scheme + '://' + request.httprequest.host


def headers(mime, portal=None, content=None):
    values = [('Content-Type', mime), ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'),
              ('Referrer-Policy', 'no-referrer'), ('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')]
    if portal:
        values.append(('Content-Security-Policy', "default-src 'none'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; media-src 'self' blob:; "
            "connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; "
            "frame-ancestors %s %s; sandbox allow-scripts allow-same-origin" % (portal, content)))
    return values


class Content(http.Controller):
    @http.route('/training/interactive/preview/<int:version_id>', auth='user', type='http', methods=['GET'])
    def preview(self, version_id, **kw):
        service = request.env['training.elearning.lease']
        portal, content = service._origins()
        if origin() != portal:
            raise Forbidden()
        version = request.env['training.elearning.version'].browse(version_id).exists()
        if not version:
            raise NotFound()
        lease, token = service._issue(version)
        return self._parent(version, lease, token, portal, content)

    def _parent(self, version, lease, token, portal, content, attempt=None):
        config = {'origin': content, 'nonce': lease.nonce, 'csrf': request.csrf_token(),
                  'attempt': attempt.id if attempt else None, 'revision': attempt.revision if attempt else 0}
        source = content + '/tm-content/' + token + '/launch'
        page = '<!doctype html><html lang="fr"><meta charset="utf-8"><title>Contenu interactif</title><h1>%s</h1>' % html.escape(version.resource_id.name)
        page += '<p>Activité formative — aucune attestation automatique.</p><p id="status" role="status">Chargement…</p>'
        page += '<iframe id="content" title="Contenu interactif" sandbox="allow-scripts allow-same-origin" referrerpolicy="no-referrer" style="width:100%%;height:70vh;border:0" src="%s"></iframe>' % html.escape(source, quote=True)
        page += '<script id="config" type="application/json">%s</script><script src="/training_management_elearning/static/src/parent.js"></script></html>' % json.dumps(config).replace('<', '\\u003c')
        return request.make_response(page, headers=headers('text/html; charset=utf-8') + [
            ('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; frame-src %s; connect-src 'self'; base-uri 'none'; frame-ancestors 'self'" % content)])

    def _lease(self, token):
        service = request.env['training.elearning.lease']
        portal, content = service._origins()
        if origin() != content:
            raise Forbidden()
        try:
            return service._resolve(token), portal, content
        except (AccessError, ValidationError):
            raise Forbidden() from None

    @http.route('/tm-content/<string:token>/file/<path:filename>', auth='public', type='http', methods=['GET'], save_session=False)
    def file(self, token, filename, **kw):
        lease, portal, content = self._lease(token)
        try:
            safe_path(filename)
        except ValueError:
            raise NotFound() from None
        record = request.env['training.elearning.file'].sudo().search([
            ('version_id', '=', lease.version_id.id), ('path', '=', filename)], limit=1)
        if not record:
            raise NotFound()
        mime = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        return request.make_response(record.data.content, headers=headers(mime, portal, content))

    @http.route('/tm-content/<string:token>/launch', auth='public', type='http', methods=['GET'], save_session=False)
    def launch(self, token, **kw):
        lease, portal, content = self._lease(token)
        version = lease.version_id
        page = '<!doctype html><meta charset="utf-8"><title>Aperçu isolé</title>'
        if version.resource_id.format == 'scorm12':
            page += '<iframe title="SCORM" style="width:100%%;height:95vh;border:0" src="/tm-content/%s/file/%s"></iframe>' % (token, html.escape(version.entrypoint))
        else:
            page += '<p>Contenu H5P contrôlé. Lecteur disponible au lot E03.</p>'
        page += '<script>parent.postMessage(%s,%s);</script>' % (json.dumps({'type':'ready','nonce':lease.nonce}), json.dumps(portal))
        return request.make_response(page, headers=headers('text/html; charset=utf-8', portal, content))
