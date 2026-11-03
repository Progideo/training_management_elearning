"""TM-specific entry, saves and renewals over the shared content controller."""
import json
import uuid
from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError, ValidationError
from werkzeug.exceptions import Forbidden
from odoo.addons.training_interactive.controllers.content import Content as CommonContent, origin


class Content(CommonContent):
    @http.route('/training/interactive/<int:enrollment_id>/<int:usage_id>',auth='user',type='http',website=True,methods=['GET'])
    def entry(self,enrollment_id,usage_id,**kw):
        portal,content=request.env['training.elearning.lease']._origins()
        if origin()!=portal:
            raise Forbidden()
        service=request.env['training.elearning.attempt']
        enrollment,usage,activity=service._scope(enrollment_id,usage_id)
        attempts=service.sudo().search([('enrollment_id','=',enrollment_id),('usage_id','=',usage_id)],order='number desc')
        acquired=request.env['training.learning.service']._complete(enrollment,activity)
        values={'title':activity.name,'objective':usage.assignment_id.objective,'version':usage.version_id.number,
            'acquired':acquired,'threshold':usage.assignment_id.threshold if usage.assignment_id.rule=='score' else None,
            'start_url':'/training/interactive/%s/%s/start' % (enrollment_id,usage_id),
            'back':'/my/trainings/%s' % enrollment_id,'request_key':str(uuid.uuid4()),'new_key':str(uuid.uuid4()),
            'attempts':[{'number':a.number,'saved':str(a.last_saved_at or 'Pas encore sauvegardée'),
                'score':('%g / %g' % (a.score,a.maximum)) if a.maximum else 'Non disponible'} for a in attempts]}
        response=request.render('training_management_elearning.interactive_entry',values)
        response.headers['Cache-Control']='no-store'
        response.headers['Referrer-Policy']='no-referrer'
        return response

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
        except (ValueError,TypeError,RecursionError,ValidationError) as error:
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
