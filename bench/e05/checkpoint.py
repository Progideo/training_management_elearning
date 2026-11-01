import json
assert env.cr.dbname=='e01'
data={}
for login in ['e05_learner','e05_peer']:
 user=env['res.users'].search([('login','=',login)])
 records=env['training.enrollment'].search([('user_id','=',user.id)])
 for enrollment in records:
  rows=env['training.learning.service'].with_user(user)._rows(enrollment)
  data[enrollment.delivery_id.name+'_'+login]={'complete':sum(r['complete'] for r in rows),'count':len(rows),
      'effective_access':enrollment._effective_state(),'activities':[{'id':r['id'],'complete':r['complete'],'available':r['available']} for r in rows]}
assert data['E05 X_e05_learner']['complete']==2
assert data['E05 X_e05_peer']['complete']==0
assert data['E05 Y_e05_learner']['complete']==0
print('E05_CHECKPOINT='+json.dumps(data,sort_keys=True))
