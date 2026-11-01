import json
from pathlib import Path
from odoo import Command
from odoo.tests import new_test_user
assert env.cr.dbname == 'e01'
assert not env['res.users'].search_count([('login','=','e05_learner')])
password=Path('/run/secrets/db_password').read_text()
coord=new_test_user(env,login='e05_coord',password=password,groups='training_management.group_training_coordinator')
learner=new_test_user(env,login='e05_learner',password=password,groups='base.group_portal')
peer=new_test_user(env,login='e05_peer',password=password,groups='base.group_portal')
customer=env['res.partner'].create({'name':'Fictional E05 customer','is_company':True})
learner.partner_id.parent_id=customer
peer.partner_id.parent_id=customer
resources={};versions={}
for kind,filename in [('h5p','fixture-v1.h5p'),('scorm12','fixture-scorm12-v1.zip')]:
 resource=env['training.elearning.resource'].with_user(coord).create({'name':'E05 '+kind,'format':kind})
 version=env['training.elearning.version'].with_user(coord)._import(resource,'1',Path('/qual/fixtures',filename).read_bytes(),'CC0 fixture, bundled library licenses retained','Fictional qualification package')
 version.action_publish();resources[kind]=resource;versions[kind]=version
programs={};deliveries={};usages={};enrollments={}
for code in ['X','Y']:
 course=env['training.course'].with_user(coord).create({'name':'E05 '+code,'company_id':env.company.id})
 course.category_id=env['training.category'].create({'name':'E05 '+code,'company_id':env.company.id})
 program=env['training.program.version'].with_user(coord).create({'course_id':course.id,'version':'1','title':'E05 '+code,
  'objectives':'Fictional practice','target_audience':'Fictional learners','prerequisites':'Reviewed','content':'Practice',
  'duration_hours':1,'delivery_mode':'elearning','language_id':env.ref('base.lang_en').id,'teaching_methods':'Practice',
  'evaluation_criteria':'Formative','access_conditions':'Native admission','accessibility_contact_id':customer.id,
  'accessibility_information':'Contact coordination'})
 program.action_validate();programs[code]=program
 delivery=env['training.delivery'].with_user(coord).create({'name':'E05 '+code,'program_id':program.id,'company_id':env.company.id,
  'kind':'autonomous','capacity':100,'access_policy':'duration','access_days':10})
 deliveries[code]=delivery
 for kind in (['h5p','scorm12'] if code=='X' else ['scorm12']):
  assignment=env['training.elearning.assignment'].with_user(coord).create({'name':code+' '+kind,'program_id':program.id,
   'version_id':versions[kind].id,'objective':'Pratiquer puis revenir à la formation','rule':'score','threshold':90 if code=='Y' else 70})
  assignment.action_validate();usages[code+'_'+kind]=assignment._apply(delivery)
 if code=='X':usages['X_scorm12'].activity_id.dependency_ids=[Command.link(usages['X_h5p'].activity_id.id)]
 for user in ([learner,peer] if code=='X' else [learner]):
  enrollment=env['training.enrollment'].with_user(coord).create({'delivery_id':delivery.id,'participant_id':user.partner_id.id,
   'user_id':user.id,'free_reason':'Fictional invitation'})
  enrollment.action_validate_prerequisites(reason='Fictional review');enrollment.action_confirm();enrollment.action_authorize(reason='Fictional authorization')
  if code=='X':enrollment.action_open_access(reason='Fictional opening')
  enrollments[code+'_'+user.login]=enrollment
path=env['training.path'].with_user(coord).create({'name':'E05 X puis Y','order_policy':'mandatory',
 'step_ids':[Command.create({'program_id':programs['X'].id,'sequence':10}),Command.create({'program_id':programs['Y'].id,'sequence':20})]})
path.action_validate()
for step,code in zip(path.step_ids.sorted('sequence'),['X','Y']):
 env['training.path.assignment'].with_user(coord).create({'step_id':step.id,'enrollment_id':enrollments[code+'_e05_learner'].id})
env.cr.commit()
print('E05_IDS='+json.dumps({'enrollments':{k:v.id for k,v in enrollments.items()},'usages':{k:v.id for k,v in usages.items()},'path':path.id,
 'versions':{k:v.id for k,v in versions.items()},'coord':coord.id,'learner':learner.id,'peer':peer.id}))
