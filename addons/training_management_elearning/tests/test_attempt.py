import uuid
from unittest.mock import patch
from odoo.tests import tagged
from odoo.exceptions import AccessError, ValidationError
from odoo.addons.training_management.tests.test_learning import LearningCase
from .test_content_security import package


class RuntimeCase(LearningCase):
    def setup_runtime(self, threshold=70):
        resource=self.env['training.elearning.resource'].with_user(self.coordinator).create({'name':'Interactive fixture','format':'scorm12'})
        version=self.env['training.elearning.version'].with_user(self.coordinator)._import(resource,'1',package(),'Test','Fictional')
        version.action_publish()
        assignment=self.env['training.elearning.assignment'].with_user(self.coordinator).create({'name':'Formative','program_id':self.program.id,
            'version_id':version.id,'objective':'Practice','rule':'score','threshold':threshold})
        assignment.action_validate()
        delivery=self.delivery()
        usage=assignment._apply(delivery)
        enrollment=self.opened(delivery)
        return enrollment,usage

    def start(self,enrollment,usage,new=False,key=None):
        return self.env['training.elearning.attempt'].with_user(self.portal)._start(enrollment.id,usage.id,key or str(uuid.uuid4()),new=new)


@tagged('post_install','-at_install')
class TestAttempt(RuntimeCase):
    def test_resume_retry_idempotence_and_conflicts(self):
        enrollment,usage=self.setup_runtime()
        key=str(uuid.uuid4())
        attempt=self.start(enrollment,usage,key=key)
        self.assertEqual(self.start(enrollment,usage,key=key),attempt)
        payload={'state':{'location':'step-1'},'result':{'score':80,'maximum':100,'completed':True}}
        receipt=attempt._save('first',1,payload)
        self.assertEqual(attempt._save('first',1,payload),receipt)
        self.assertEqual(attempt.sudo().revision,1)
        self.assertEqual(len(attempt.sudo().event_ids),1)
        with self.assertRaises(ValidationError): attempt._save('first',1,{'state':{}})
        with self.assertRaises(ValidationError): attempt._save('late',1,{'state':{}})
        self.assertEqual(attempt._snapshot()['state'],{'location':'step-1'})
        new=self.start(enrollment,usage,new=True)
        self.assertEqual(new.sudo().number,2)
        self.assertEqual(new._snapshot()['state'],{})
        with self.assertRaises(ValidationError): attempt._save('old',2,{'state':{}})
        with self.assertRaises(AccessError): attempt.with_user(self.peer)._snapshot()
        with self.assertRaises(AccessError): self.env['training.elearning.attempt'].with_user(self.portal).search([])
        with self.assertRaises(ValidationError): new._save('nan',1,{'result':{'score':float('nan'),'maximum':100,'completed':True}})
        with self.assertRaises(ValidationError): new._save('string',1,{'result':{'score':80,'maximum':100,'completed':'false'}})

    def test_atomic_savepoint_and_retry_after_failure(self):
        enrollment,usage=self.setup_runtime()
        attempt=self.start(enrollment,usage)
        payload={'result':{'score':80,'maximum':100,'completed':True}}
        original=type(attempt)._project
        def fail_after_projection(record,event):
            original(record,event)
            raise ValidationError('Injected failure after native projection')
        with patch.object(type(attempt),'_project',new=fail_after_projection):
            with self.assertRaises(ValidationError): attempt._save('first',1,payload)
        self.assertEqual(attempt.sudo().revision,0)
        self.assertFalse(attempt.sudo().event_ids)
        self.assertFalse(self.service()._progress(enrollment,usage.activity_id))
        attempt._save('first',1,payload)
        self.assertEqual(attempt.sudo().revision,1)
