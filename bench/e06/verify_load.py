assert env.cr.dbname in ('e01','e01_restore')
attempts=env['training.elearning.attempt'].sudo().search([('actor_id.login','=like','e06_load_%')])
assert len(attempts)==50,len(attempts)
assert all(a.revision==1 and a.completed and a.score==100 for a in attempts)
assert all(len(a.event_ids)==1 for a in attempts)
for a in attempts:
 p=env['training.learning.service']._progress(a.enrollment_id,a.usage_id.activity_id)
 assert p.completed and p.elearning_event_id.attempt_id==a
print('PASS: 50 independent attempts, 50 original events despite replay, 50 matching native acquisitions')
