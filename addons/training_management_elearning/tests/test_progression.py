from unittest.mock import patch
from odoo import Command
from odoo.tests import tagged
from odoo.exceptions import AccessError, ValidationError
from .test_attempt import RuntimeCase


@tagged('post_install','-at_install')
class TestFormativeProgress(RuntimeCase):
    def result(self,attempt,key,revision,score):
        return attempt._save(key,revision,{'result':{'score':score,'maximum':100,'completed':True}})

    def test_independent_rules_retry_invalidation_and_human_criterion(self):
        enrollment,usage=self.setup_runtime()
        attempt=self.start(enrollment,usage)
        human=self.activity(enrollment.delivery_id,criterion='validation')
        self.result(attempt,'pass',1,80)
        progress=self.service()._progress(enrollment,usage.activity_id)
        event=progress.elearning_event_id
        self.assertTrue(progress.completed)
        self.assertFalse(self.service()._complete(enrollment,human))
        next_attempt=self.start(enrollment,usage,new=True)
        self.result(next_attempt,'lower',1,40)
        self.assertTrue(progress.completed)
        self.assertEqual(progress.elearning_event_id,event)
        other=self.env['training.elearning.assignment'].with_user(self.coordinator).create({'name':'Higher threshold',
            'program_id':self.program.id,'version_id':usage.version_id.id,'objective':'Practice','rule':'score','threshold':90})
        other.action_validate()
        y_delivery=self.delivery();y_usage=other._apply(y_delivery);y_enrollment=self.opened(y_delivery)
        y=self.start(y_enrollment,y_usage)
        self.result(y,'insufficient',1,80)
        self.assertFalse(self.service()._complete(y_enrollment,y_usage.activity_id))
        with self.assertRaises(AccessError): progress.with_user(self.portal)._invalidate_formative('forged')
        progress.with_user(self.coordinator)._invalidate_formative('Fictional correction')
        self.assertFalse(progress.completed)
        self.assertTrue(event.exists())
        self.result(next_attempt,'old-after-invalidation',2,100)
        self.assertFalse(progress.completed)
        third=self.start(enrollment,usage,new=True);self.result(third,'new-success',1,100)
        self.assertTrue(progress.completed)
        source=self.service()._certificate_origin(enrollment,usage.activity_id)
        self.assertEqual(source['formative']['content_version'],usage.version_id.id)

    def test_path_cache_x_y_and_atomic_projection(self):
        enrollment,usage=self.setup_runtime()
        course_y=self.env['training.course'].create({'name':'Fictional Y','category_id':self.course.category_id.id})
        program_y=self.program.copy({'version':'Y1','course_id':course_y.id});program_y.action_validate()
        y_delivery=self.delivery(program_id=program_y.id)
        y_activity=self.activity(y_delivery)
        y_enrollment=self.admitted(y_delivery)
        path=self.env['training.path'].with_user(self.coordinator).create({'name':'X then Y','order_policy':'mandatory'})
        steps=self.env['training.path.step'].with_user(self.coordinator).create([
            {'path_id':path.id,'program_id':self.program.id,'sequence':10},
            {'path_id':path.id,'program_id':program_y.id,'sequence':20}])
        path.action_validate()
        self.env['training.path.assignment'].with_user(self.coordinator).create({'step_id':steps[0].id,'enrollment_id':enrollment.id})
        yref=self.env['training.path.assignment'].with_user(self.coordinator).create({'step_id':steps[1].id,'enrollment_id':y_enrollment.id})
        self.assertTrue(yref.blocked)
        attempt=self.start(enrollment,usage)
        self.result(attempt,'pass',1,80)
        self.assertFalse(yref.blocked)
        self.assertFalse(self.service()._complete(y_enrollment,y_activity))

    def test_declared_result_does_not_decide_the_completion_certificate_by_default(self):
        enrollment,usage=self.setup_runtime()
        service=self.env['training.learning.service'].with_user(self.coordinator)
        activity=usage.activity_id
        self.assertFalse(service._required_for_certificate(activity))
        other=self.activity(enrollment.delivery_id,criterion='validation')
        self.assertTrue(service._required_for_certificate(other))
        counted=self.env['training.elearning.assignment'].with_user(self.coordinator).create({'name':'Counted',
            'program_id':self.program.id,'version_id':usage.version_id.id,'objective':'Practice','rule':'completed','counts_for_completion':True})
        counted.action_validate()
        counted_usage=counted._apply(self.delivery())
        self.assertTrue(service._required_for_certificate(counted_usage.activity_id))

