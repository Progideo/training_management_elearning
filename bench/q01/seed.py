import json
from pathlib import Path
from odoo.tests import new_test_user
assert env.cr.dbname == 'e01'
coord=env['res.users'].search([('login','=','e05_coord')])
learner=new_test_user(env,login='q01_learner',password=Path('/run/secrets/db_password').read_text(),groups='base.group_portal')
customer=env['res.partner'].create({'name':'Fictional Q01 customer','is_company':True})
learner.partner_id.parent_id=customer
course=env['training.course'].with_user(coord).create({'name':'Q01 interactions','company_id':env.company.id})
course.category_id=env['training.category'].create({'name':'Q01','company_id':env.company.id})
program=env['training.program.version'].with_user(coord).create({'course_id':course.id,'version':'1','title':'Q01 interactions',
 'objectives':'Fictional practice','target_audience':'Fictional learners','prerequisites':'Reviewed','content':'Practice',
 'duration_hours':1,'delivery_mode':'elearning','language_id':env.ref('base.lang_en').id,'teaching_methods':'Practice',
 'evaluation_criteria':'Mock exam','access_conditions':'Native admission','accessibility_contact_id':customer.id,
 'accessibility_information':'Contact coordination'})
program.action_validate()
delivery=env['training.delivery'].with_user(coord).create({'name':'Q01 interactions','program_id':program.id,'company_id':env.company.id,
 'kind':'autonomous','capacity':10,'access_policy':'duration','access_days':10})
exam=env['survey.survey'].with_user(coord).create({'title':'Appariement et mise en ordre','training_program_id':program.id,
 'survey_type':'custom','scoring_type':'scoring_with_answers','time_limit':60,'scoring_success_min':75})
questions=[]
for i,(kind,title,items) in enumerate([('matching','Associez les animaux','Chat | Cat\nChien | Dog\nOiseau | Bird'),('ordering','Ordonnez les étapes','Préparer\nExécuter\nVérifier')]):
 q=env['survey.question'].with_user(coord).create({'survey_id':exam.id,'title':title,'question_type':'multiple_choice','sequence':i*10,
  'answer_score':6,'training_theme':kind,'training_explanation':'Explication finale privée Q01'})
 wizard=env['training.elearning.question.configure'].with_user(coord).create({'question_id':q.id,'kind':kind,'items':items})
 wizard.action_configure();questions.append(q)
exam.action_training_publish()
activity=env['training.learning.activity'].with_user(coord).create({'name':'Examen enrichi','delivery_id':delivery.id,'criterion':'evaluation','evaluation_threshold':75,'training_exam_id':exam.id})
enrollment=env['training.enrollment'].with_user(coord).create({'delivery_id':delivery.id,'participant_id':learner.partner_id.id,'user_id':learner.id,'free_reason':'Fictional invitation'})
enrollment.action_validate_prerequisites(reason='Fictional review');enrollment.action_confirm();enrollment.action_authorize(reason='Fictional authorization');enrollment.action_open_access(reason='Fictional opening')
env.cr.commit()
print('Q01_IDS='+json.dumps({'enrollment':enrollment.id,'activity':activity.id,'exam':exam.id,'questions':[{'id':q.id,'correct':q.suggested_answer_ids.filtered('is_correct').sorted('training_row_key').ids} for q in questions]}))
