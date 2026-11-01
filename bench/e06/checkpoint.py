import json,hashlib
from pathlib import Path
assert env.cr.dbname in ('e01','e01_restore')
data={}
for model,columns in {
 'training.elearning.version':['resource_id','number','state','sha256'],
 'training.elearning.usage':['assignment_id','activity_id','version_id'],
 'training.elearning.attempt':['enrollment_id','usage_id','number','revision','score','maximum','completed','state_json'],
 'training.elearning.event':['attempt_id','key','sha256','receipt_json'],
 'training.learning.progress':['enrollment_id','activity_id','completed','revision','elearning_event_id'],
}.items():
 data[model]=env[model].sudo().search([],order='id').read(columns)
data['package_bytes']=[(f.id,hashlib.sha256(f.data.content).hexdigest()) for f in env['training.elearning.file'].sudo().search([],order='id')]
filestore=Path('/var/lib/odoo/filestore')/env.cr.dbname
data['filestore']={str(p.relative_to(filestore)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(filestore.rglob('*')) if p.is_file() and 'checklist' not in p.parts}
print('E06_CHECKPOINT='+json.dumps(data,sort_keys=True,default=str))
