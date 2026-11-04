import json
assert env.cr.dbname == 'e00_fresh'
models = {
 'training.elearning.resource': ['name','identifier','company_id','active','format','license_note'],
 'training.course': ['name','company_id'],
 'training.program.version': ['title','version','course_id'],
 'training.delivery': ['name','program_id'],
 'training.enrollment': ['delivery_id','participant_id','user_id','state'],
 'training.learning.activity': ['name','delivery_id','criterion'],
 'training.learning.progress': ['enrollment_id','activity_id','completed','revision'],
}
data = {model: env[model].with_context(active_test=False).search([],order='id').read(fields) for model, fields in models.items()}
data['addon_xmlids'] = env['ir.model.data'].search([('module','=','training_management_interactive')],order='name').read(['name','model','res_id'])
assert len(data['training.elearning.resource']) == 1
assert len(data['training.enrollment']) == 1
assert len(data['training.learning.activity']) == 2
assert sum(p['completed'] for p in data['training.learning.progress']) == 1
assert env['ir.module.module'].search([('name','=','website_slides')]).state == 'uninstalled'
assert env['ir.module.module'].search([('name','=','training_management_survey')]).state == 'installed'
print('E00_CHECKPOINT='+json.dumps(data,sort_keys=True))
