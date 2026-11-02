import json
# Extend the existing runtime checkpoint with editorial audit and native exam history.
result={}
for model,columns in {
 'training.elearning.version':['resource_id','number','state','sha256','withdrawal_reason','withdrawn_at','withdrawn_by_id'],
 'survey.user_input':['survey_id','state','training_enrollment_id','scoring_percentage','deadline'],
 'survey.user_input.line':['user_input_id','question_id','suggested_answer_id','answer_score'],
}.items():
 result[model]=env[model].sudo().search([],order='id').read(columns)
print('REVIEW_CHECKPOINT='+json.dumps(result,sort_keys=True,default=str))
