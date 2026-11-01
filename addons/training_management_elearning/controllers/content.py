import html
import json
import mimetypes
import uuid
from pathlib import Path
from datetime import timedelta
from odoo import fields
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
                  'attempt': attempt.id if attempt else None, 'revision': attempt.sudo().revision if attempt else 0, 'lease':lease.id}
        source = content + '/tm-content/' + token + '/launch'
        page = '<!doctype html><html lang="fr"><meta charset="utf-8"><title>Contenu interactif</title><h1>%s</h1>' % html.escape(version.resource_id.name)
        page += '<p>Activité formative — aucune attestation automatique.</p><p id="status" role="status">Chargement…</p>'
        page += '<iframe id="content" title="Contenu interactif" sandbox="allow-scripts allow-same-origin" referrerpolicy="no-referrer" style="width:100%%;height:70vh;border:0" src="%s"></iframe>' % html.escape(source, quote=True)
        if attempt:
            page += '<p><a href="/my/trainings/%s">Revenir à ma formation</a></p>' % attempt.sudo().enrollment_id.id
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
        snapshot=lease.attempt_id.with_user(lease.user_id)._snapshot() if lease.attempt_id else {'state':{}}
        config={'kind':version.resource_id.format,'version':version.id,'entrypoint':version.entrypoint,
                'state':snapshot['state'],'nonce':lease.nonce,'portal':portal}
        root='/tm-content/'+token
        page='<!doctype html><html lang="fr"><meta charset="utf-8"><title>Lecteur isolé</title><div id="player"></div>'
        page+='<script id="config" type="application/json">%s</script>' % json.dumps(config).replace('<','\\u003c')
        vendor='h5p/main.bundle.js' if config['kind']=='h5p' else 'scorm12.min.js'
        page+='<script src="%s/vendor/%s"></script><script src="%s/runner.js"></script></html>' % (root,vendor,root)
        return request.make_response(page, headers=headers('text/html; charset=utf-8', portal, content))

    @http.route('/tm-content/<string:token>/vendor/<path:filename>', auth='public', type='http', methods=['GET'], save_session=False)
    def vendor(self, token, filename, **kw):
        lease, portal, content=self._lease(token)
        try:
            safe_path(filename)
        except ValueError:
            raise NotFound() from None
        root=Path(__file__).resolve().parents[1]/'vendor'
        path=(root/filename).resolve()
        if root not in path.parents or not path.is_file() or path.suffix not in ('.js','.css','.woff','.woff2','.ttf','.svg','.png','.gif'):
            raise NotFound()
        return request.make_response(path.read_bytes(),headers=headers(mimetypes.guess_type(filename)[0] or 'application/octet-stream',portal,content))

    @http.route('/tm-content/<string:token>/runner.js', auth='public', type='http', methods=['GET'], save_session=False)
    def runner(self, token, **kw):
        lease, portal, content=self._lease(token)
        data=(Path(__file__).resolve().parents[1]/'static/src/runner.js').read_bytes()
        return request.make_response(data,headers=headers('application/javascript',portal,content))

    @http.route('/training/interactive/<int:enrollment_id>/<int:usage_id>/start',auth='user',type='http',methods=['POST'])
    def start(self,enrollment_id,usage_id,**values):
        portal,content=request.env['training.elearning.lease']._origins()
        if origin()!=portal:
            raise Forbidden()
        attempt=request.env['training.elearning.attempt']._start(enrollment_id,usage_id,values.get('request_key',''),new=values.get('new')=='1')
        return request.redirect('/training/interactive/attempt/%s' % attempt.id,code=303)

    @http.route('/training/interactive/attempt/<int:attempt_id>',auth='user',type='http',methods=['GET'])
    def attempt(self,attempt_id,**kw):
        service=request.env['training.elearning.lease']
        portal,content=service._origins()
        if origin()!=portal:
            raise Forbidden()
        attempt=request.env['training.elearning.attempt'].browse(attempt_id)
        attempt._authorize()
        version=attempt.sudo().version_id
        lease,token=service._issue(version,attempt)
        return self._parent(version,lease,token,portal,content,attempt)

    @http.route('/training/interactive/attempt/<int:attempt_id>/save',auth='user',type='http',methods=['POST'])
    def save(self,attempt_id,**values):
        if origin()!=request.env['training.elearning.lease']._origins()[0]:
            raise Forbidden()
        raw=values.get('payload','')
        if len(raw)>140000:
            return request.make_json_response({'ok':False,'error':'Report too large'},status=413)
        try:
            data=json.loads(raw)
            if not isinstance(data,dict):
                raise ValidationError('Invalid report')
            receipt=request.env['training.elearning.attempt'].browse(attempt_id)._save(data.get('key'),data.get('revision'),data.get('data'))
            return request.make_json_response(receipt,headers=[('Cache-Control','no-store')])
        except (ValueError,TypeError,ValidationError) as error:
            return request.make_json_response({'ok':False,'error':str(error)},status=409,headers=[('Cache-Control','no-store')])
        except AccessError:
            raise Forbidden() from None

    @http.route('/training/interactive/attempt/<int:attempt_id>/renew',auth='user',type='http',methods=['POST'])
    def renew(self,attempt_id,**values):
        if origin()!=request.env['training.elearning.lease']._origins()[0]:
            raise Forbidden()
        attempt=request.env['training.elearning.attempt'].browse(attempt_id)
        attempt._authorize()
        try:
            lease=request.env['training.elearning.lease'].sudo().browse(int(values.get('lease','0'))).exists()
        except ValueError:
            raise Forbidden() from None
        if not lease or lease.user_id != request.env.user or lease.attempt_id.id!=attempt_id:
            raise Forbidden()
        lease._renew()
        return request.make_json_response({'ok':True},headers=[('Cache-Control','no-store')])
