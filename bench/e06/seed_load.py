import json
from pathlib import Path
from odoo.tests import new_test_user
assert env.cr.dbname=='e01'
coord=env['res.users'].search([('login','=','e05_coord')])
delivery=env['training.delivery'].search([('name','=','E05 Y')]);assert len(delivery)==1
usage=env['training.elearning.usage'].search([('delivery_id','=',delivery.id)]);assert len(usage)==1
users=[]
for i in range(50):
 login='e06_load_%02d'%i
 user=new_test_user(env,login=login,password=Path('/run/secrets/db_password').read_text(),groups='base.group_portal')
 enrollment=env['training.enrollment'].with_user(coord).create({'delivery_id':delivery.id,'participant_id':user.partner_id.id,'user_id':user.id,'free_reason':'Fictional load test'})
 enrollment.action_validate_prerequisites(reason='Fictional');enrollment.action_confirm();enrollment.action_authorize(reason='Fictional');enrollment.action_open_access(reason='Fictional')
 users.append({'login':login,'enrollment':enrollment.id,'usage':usage.id})
env.cr.commit()
print('E06_USERS='+json.dumps(users))
